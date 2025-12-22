from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import calendar
import csv
import os
import re

HORIZON_H_MONTHS = 2
HORIZON_H_WEEKS = 10
POST_DEFAULT_CAPACITY_HOURS_WEEK = 35
ADVANCE_RETREAT_WEEKS = 3
ENCODING_CANDIDATES = ("utf-8-sig", "cp1252", "latin-1", "utf-8")


def norm_code(x: str) -> str:
    if x is None:
        return ""
    s = str(x).replace("\ufeff", "")
    s = "".join(s.split())
    return s.upper()


def detect_csv_delimiter(filepath, fallback=',', sample_size=65536):
    candidates = [b'\t', b';', b'|', b',', b':', b'^']
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
    except FileNotFoundError:
        return fallback
    except Exception:
        return fallback
    counts = {d: sample.count(d) for d in candidates}
    if all(c == 0 for c in counts.values()):
        return fallback
    try:
        lines = sample.splitlines()[:50]
        scored = []
        for d in candidates:
            if counts[d] == 0:
                continue
            splits = [ln.count(d) + 1 for ln in lines if ln.strip()]
            if not splits:
                continue
            avg_cols = sum(splits) / len(splits)
            var_cols = sum((c - avg_cols) ** 2 for c in splits) / len(splits)
            score = counts[d] - var_cols
            if avg_cols >= 2:
                scored.append((score, d))
        if scored:
            scored.sort(reverse=True)
            winner = scored[0][1]
            return winner.decode('ascii') if isinstance(winner, bytes) else winner
    except Exception:
        pass
    winner = max(counts.items(), key=lambda kv: kv[1])[0]
    return winner.decode('ascii') if isinstance(winner, bytes) else winner


def _make_reader(filepath, required_cols=None, fallback=','):
    delim = detect_csv_delimiter(filepath, fallback=fallback)
    last_err = None
    for enc in ENCODING_CANDIDATES:
        try:
            f = open(filepath, "r", encoding=enc, newline="")
            reader = csv.DictReader(f, delimiter=delim)
            _ = reader.fieldnames
            if not _:
                f.close()
                continue
            if required_cols is not None and not all(col in _ for col in required_cols):
                pass
            return f, reader, delim, enc
        except FileNotFoundError:
            return None, None, fallback, None
        except UnicodeDecodeError as e:
            last_err = e
            try:
                f.close()
            except Exception:
                pass
            continue
        except Exception as e:
            last_err = e
            try:
                f.close()
            except Exception:
                pass
            continue
    if last_err:
        raise last_err
    return None, None, fallback, None


def try_parse_float(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        raise ValueError("Cannot parse None as float.")
    text = str(value).strip()
    if not text:
        raise ValueError("Cannot parse empty string as float.")
    sanitized = text.replace('\u00a0', '').replace(' ', '')
    if sanitized.count(',') > 0 and sanitized.count('.') > 0:
        sanitized = sanitized.replace('.', '')
    sanitized = sanitized.replace(',', '.')
    return float(sanitized)


class ManufacturingOrder:
    def __init__(
        self,
        id,
        designation,
        product_id,
        product_type,
        bom_level,
        need_date_str,
        quantity,
        fg,
        cat,
        us,
        fs,
        unit="U",
        status="UNASSIGNED"
    ):
        self.id = id
        self.designation = designation
        self.product_id = product_id
        self.product_type = product_type
        self.bom_level = int(bom_level)

        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                parsed = datetime.strptime(need_date_str, fmt)
                break
            except ValueError:
                continue
        if not parsed:
            raise ValueError(f"Date format for {need_date_str} not recognized.")
        self.need_date = parsed

        self.source_qty = str(quantity) if quantity is not None else ""
        self.quantity = try_parse_float(quantity)
        self.unit = unit

        self.assigned_group_id = None
        self.status = "UNASSIGNED"
        self.scheduled_start_date = None
        self.scheduled_end_date = None

        self.fg = fg
        self.cat = cat
        self.us = us
        self.fs = fs

        self.individual_product_stock = 0

    def __repr__(self):
        lvl = getattr(self, "effective_bom_level", self.bom_level)
        return (
            f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.product_id}', "
            f"type='{self.product_type}', level={lvl}, "
            f"need={self.need_date.strftime('%Y-%m-%d')}, qty={self.quantity}, "
            f"fg='{self.fg}', cat='{self.cat}', indiv_stock={self.individual_product_stock}, "
            f"group={self.assigned_group_id}, status='{self.status}')"
        )


class BOMEntry:
    def __init__(
        self,
        parent_product_id,
        child_product_id,
        quantity_child_per_parent,
        child_bom_level,
        parent_bom_level=None,
    ):
        self.parent_product_id = parent_product_id
        self.child_product_id = child_product_id
        self.quantity_child_per_parent = try_parse_float(quantity_child_per_parent)

        try:
            self.child_bom_level = int(child_bom_level) if child_bom_level not in (None, "") else 0
        except Exception:
            self.child_bom_level = 0

        if parent_bom_level not in (None, ""):
            try:
                self.parent_bom_level = int(parent_bom_level)
            except Exception:
                self.parent_bom_level = 0
        else:
            self.parent_bom_level = 0

    def __repr__(self):
        return (
            f"BOM(parent='{self.parent_product_id}' uses "
            f"{self.quantity_child_per_parent} of child='{self.child_product_id}' "
            f"(child_lvl={self.child_bom_level}, parent_lvl={self.parent_bom_level}))"
        )


class Group:
    def __init__(
        self,
        id,
        ps_product_id,
        initial_ps_of,
        window_start_date,
        window_end_date,
        initial_ps_as_stock=False
    ):
        self.id = id
        self.ps_product_id = ps_product_id
        self.time_window_start = window_start_date
        self.time_window_end = window_end_date

        self.ofs = []
        self.current_ps_stock_available = 0

        self.component_stocks = {}
        self.individual_product_stocks = {}
        self.product_consumption = {}

        ps_q = initial_ps_of.quantity if initial_ps_as_stock else 0
        self.add_of(initial_ps_of, ps_quantity_change=ps_q)

    def add_of(self, of_to_add, ps_quantity_change=0):
        self.ofs.append(of_to_add)
        self.current_ps_stock_available += ps_quantity_change

        if of_to_add.product_id not in self.component_stocks:
            self.component_stocks[of_to_add.product_id] = 0
        self.component_stocks[of_to_add.product_id] += ps_quantity_change

        product_id = of_to_add.product_id
        if product_id not in self.individual_product_stocks:
            self.individual_product_stocks[product_id] = 0
        if product_id not in self.product_consumption:
            self.product_consumption[product_id] = 0

        of_to_add.individual_product_stock = 0
        of_to_add.assigned_group_id = self.id
        of_to_add.status = "ASSIGNED"

    def calculate_consumption(self, bom_data):
        from collections import defaultdict as _dd

        def norm(x: str) -> str:
            if x is None:
                return ""
            s = str(x).replace('\ufeff', '')
            s = ''.join(s.split())
            return s.upper()

        if not self.ofs:
            self.component_stocks = {}
            self.individual_product_stocks = {}
            for of in getattr(self, "ofs", []):
                of.individual_product_stock = 0.0
            return

        product_level = {}

        for bom in bom_data:
            p = norm(bom.parent_product_id)
            c = norm(bom.child_product_id)

            try:
                c_lvl = int(getattr(bom, "child_bom_level", 0) or 0)
            except Exception:
                c_lvl = 0

            try:
                p_lvl = int(getattr(bom, "parent_bom_level", 0) or 0)
            except Exception:
                p_lvl = 0

            if c and c_lvl > 0:
                product_level[c] = c_lvl if c not in product_level else max(product_level[c], c_lvl)
            if p and p_lvl > 0:
                product_level[p] = p_lvl if p not in product_level else max(product_level[p], p_lvl)

        produced_qty = _dd(float)
        for of in self.ofs:
            pid = norm(of.product_id)
            produced_qty[pid] += float(of.quantity)

        if not produced_qty:
            self.component_stocks = {}
            self.individual_product_stocks = {}
            for of in self.ofs:
                of.individual_product_stock = 0.0
            return

        for pid in produced_qty.keys():
            if pid not in product_level:
                product_level[pid] = 0

        levels_in_group = {product_level.get(pid, 0) for pid in produced_qty.keys()}
        max_level = max(levels_in_group) if levels_in_group else 0
        min_level = min(levels_in_group) if levels_in_group else 0

        bom_by_parent = _dd(list)
        for bom in bom_data:
            p = norm(bom.parent_product_id)
            c = norm(bom.child_product_id)
            if not p or not c:
                continue
            if p in produced_qty:
                bom_by_parent[p].append((c, float(bom.quantity_child_per_parent)))

        product_stock = {pid: 0.0 for pid in produced_qty.keys()}
        product_consumption = _dd(float)

        for lvl in range(max_level, min_level - 1, -1):
            for pid, plvl in product_level.items():
                if plvl != lvl:
                    continue
                if pid not in produced_qty:
                    continue

                qty_prod = produced_qty[pid]
                if qty_prod <= 0:
                    continue

                product_stock[pid] = product_stock.get(pid, 0.0) + qty_prod

                for child_id, q_child in bom_by_parent.get(pid, []):
                    if child_id not in produced_qty:
                        continue
                    need = qty_prod * q_child
                    product_stock[child_id] = product_stock.get(child_id, 0.0) - need
                    product_consumption[child_id] += need

        remaining_per_of = {of.id: 0.0 for of in self.ofs}

        for prod_norm in produced_qty.keys():
            stock_left = max(0.0, product_stock.get(prod_norm, 0.0))

            ofs_same_product = [of for of in self.ofs if norm(of.product_id) == prod_norm]
            ofs_same_product_sorted = sorted(
                ofs_same_product,
                key=lambda o: (o.need_date, o.id)
            )

            for of in ofs_same_product_sorted:
                if stock_left <= 0:
                    break
                assign = min(stock_left, float(of.quantity))
                remaining_per_of[of.id] = assign
                stock_left -= assign

        for of in self.ofs:
            of.individual_product_stock = max(0.0, remaining_per_of.get(of.id, 0.0))

        self.product_consumption = dict(product_consumption)
        self.individual_product_stocks = {
            pid: sum(
                of.individual_product_stock
                for of in self.ofs
                if norm(of.product_id) == pid
            )
            for pid in {norm(of.product_id) for of in self.ofs}
        }
        self.component_stocks = dict(product_stock)


class Post:
    """Poste avec capacité hebdomadaire et indisponibilités."""
    def __init__(
        self,
        id,
        name,
        default_capacity_hours_week=POST_DEFAULT_CAPACITY_HOURS_WEEK,
        weekly_capacity_by_week=None,
    ):
        self.id = id
        self.name = name

        self.work_start_time = time(0, 0)
        self.work_end_time = time(23, 59)
        self.lunch_start_time = time(0, 0)
        self.lunch_end_time = time(0, 0)

        self.daily_capacity_hours = 24.0

        self.default_capacity_hours_week = float(default_capacity_hours_week or 0)
        self.weekly_capacity_by_week = weekly_capacity_by_week or {}

        from collections import defaultdict as _dd
        self.weekly_load_hours = _dd(float)

        self.unavailable_periods = []
        self.scheduled_slots = []

        self.planning_start_monday = None

    def set_week0_monday(self, monday_date):
        self.planning_start_monday = monday_date

    def _ensure_planning_start(self, dt_obj: datetime):
        if self.planning_start_monday is None:
            d = dt_obj.date()
            self.planning_start_monday = d - timedelta(days=d.weekday())

    def _relative_week_index(self, dt_obj: datetime) -> int:
        self._ensure_planning_start(dt_obj)
        delta_days = (dt_obj.date() - self.planning_start_monday).days
        if delta_days < 0:
            return 1
        return 1 + (delta_days // 7)

    def _week_key(self, dt_obj: datetime):
        return self._relative_week_index(dt_obj)

    def _allowed_hours_for_week(self, dt_obj: datetime) -> float:
        w = self._relative_week_index(dt_obj)
        return float(self.weekly_capacity_by_week.get(w, self.default_capacity_hours_week))

    def _weekly_hours_distribution(self, start_dt: datetime, end_dt: datetime):
        from collections import defaultdict as _dd
        dist = _dd(float)
        current = start_dt

        while current < end_dt:
            wk = self._week_key(current)
            monday_of_week = self.planning_start_monday + timedelta(days=7 * (wk - 1))
            week_end_dt = datetime.combine(monday_of_week + timedelta(days=7), time.min)
            segment_end = min(end_dt, week_end_dt)
            hours = (segment_end - current).total_seconds() / 3600.0
            dist[wk] += hours
            current = segment_end

        return dist

    def _can_add_slot_in_week(self, start_dt: datetime, end_dt: datetime) -> bool:
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, add_hours in dist.items():
            monday_of_week = self.planning_start_monday + timedelta(days=7 * (wk - 1))
            dt_for_wk = datetime.combine(monday_of_week, time.min)
            allowed = self._allowed_hours_for_week(dt_for_wk)
            used = self.weekly_load_hours[wk]
            if used + add_hours > allowed + 1e-6:
                return False
        return True

    def _register_slot_in_week_load(self, start_dt: datetime, end_dt: datetime):
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, hours in dist.items():
            self.weekly_load_hours[wk] += hours

    def _recompute_weekly_load_from_slots(self):
        from collections import defaultdict as _dd
        self.weekly_load_hours = _dd(float)
        for s, e, _ in self.scheduled_slots:
            dist = self._weekly_hours_distribution(s, e)
            for wk, hours in dist.items():
                self.weekly_load_hours[wk] += hours

    def add_unavailable_period(self, start_date_str, end_date_str):
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0
            )
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
            if end_dt < start_dt:
                return
            self.unavailable_periods.append((start_dt, end_dt))
            self.unavailable_periods.sort()
        except ValueError:
            pass

    def _is_working_moment(self, dt_obj: datetime):
        if dt_obj.weekday() >= 5:
            return False
        for un_start, un_end in self.unavailable_periods:
            if un_start <= dt_obj <= un_end:
                return False
        return True

    def _get_next_working_datetime(self, current_dt_orig: datetime):
        current_dt = current_dt_orig
        max_iterations = 10000
        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            current_dt = current_dt.replace(second=0, microsecond=0)

            if current_dt.weekday() >= 5:
                days_to_next_monday = (7 - current_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                current_dt = (current_dt + timedelta(days=days_to_next_monday)).replace(
                    hour=0, minute=0
                )
                continue

            moved = False
            for un_start, un_end in self.unavailable_periods:
                if un_start <= current_dt <= un_end:
                    current_dt = un_end + timedelta(minutes=1)
                    moved = True
                    break
            if moved:
                continue

            if self._is_working_moment(current_dt):
                return current_dt

            current_dt += timedelta(minutes=1)

        return current_dt_orig

    def calculate_end_datetime(self, start_dt_param: datetime, duration_hours: float):
        if duration_hours <= 0:
            return start_dt_param

        actual_start_dt = self._get_next_working_datetime(start_dt_param)
        current_dt = actual_start_dt
        remaining_seconds = duration_hours * 3600
        max_calc_iterations = 200000
        calc_iter = 0

        while remaining_seconds > 0 and calc_iter < max_calc_iterations:
            calc_iter += 1
            if not self._is_working_moment(current_dt):
                current_dt = self._get_next_working_datetime(current_dt)
                continue

            next_minute_dt = current_dt + timedelta(minutes=1)
            seconds_this_minute = 60
            can_consume_seconds = min(remaining_seconds, seconds_this_minute)
            remaining_seconds -= can_consume_seconds
            current_dt = next_minute_dt

        if remaining_seconds > 0:
            return datetime.max
        return current_dt

    def find_available_slot(self, search_start_dt_param: datetime, duration_hours: float, of_id_to_ignore=None):
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = search_start_dt_param + timedelta(days=365)

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                current_try_start_dt = self._get_next_working_datetime(
                    current_try_start_dt + timedelta(days=1)
                )
                continue

            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(
                    hour=0, minute=0
                )
                current_try_start_dt = self._get_next_working_datetime(next_week_monday)
                continue

            is_overlap = False
            for booked_start, booked_end, booked_of_id in self.scheduled_slots:
                if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                    continue
                if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                    is_overlap = True
                    current_try_start_dt = self._get_next_working_datetime(booked_end)
                    break

            if not is_overlap:
                return current_try_start_dt, potential_end_dt

        return None, None

    def book_slot(self, start_dt: datetime, end_dt: datetime, of_id):
        self.clear_schedule_for_of(of_id)
        self.scheduled_slots.append((start_dt, end_dt, of_id))
        self.scheduled_slots.sort()
        self._register_slot_in_week_load(start_dt, end_dt)

    def clear_schedule_for_of(self, of_id):
        if not self.scheduled_slots:
            return
        self.scheduled_slots = [
            (s, e, o) for (s, e, o) in self.scheduled_slots if o != of_id
        ]
        self._recompute_weekly_load_from_slots()

    def __repr__(self):
        return (
            f"Post(id={self.id}, name='{self.name}', "
            f"daily_hours={self.daily_capacity_hours:.2f}, "
            f"unavailable_periods={len(self.unavailable_periods)}, "
            f"scheduled_slots={len(self.scheduled_slots)})"
        )


class Operation:
    def __init__(self, product_key, operation_name, post_id, standard_time_hours, sequence, priority):
        self.product_key = product_key
        self.operation_name = operation_name
        self.post_id = post_id
        self.standard_time_hours = try_parse_float(standard_time_hours)
        self.sequence = int(sequence)
        self.priority = int(priority)


def find_qty_of_component_in_product(product_to_make_id, component_to_find_id, bom_data, memo=None):
    if memo is None:
        memo = {}
    key = (product_to_make_id, component_to_find_id)
    if key in memo:
        return memo[key]
    if product_to_make_id == component_to_find_id:
        memo[key] = 1.0
        return 1.0

    total_component_needed = 0.0
    direct_components = [b for b in bom_data if b.parent_product_id == product_to_make_id]
    for bom_line in direct_components:
        qty_in_child = find_qty_of_component_in_product(
            bom_line.child_product_id,
            component_to_find_id,
            bom_data,
            memo
        )
        total_component_needed += bom_line.quantity_child_per_parent * qty_in_child

    memo[key] = total_component_needed
    return total_component_needed


def sort_ofs_for_grouping(of_list):
    return sorted(
        of_list,
        key=lambda of: (of.designation, -getattr(of, "effective_bom_level", 0), of.need_date)
    )


def _norm(x: str) -> str:
    return ''.join(str(x or '').split()).upper()


def build_bom_graph(bom_data):
    G = defaultdict(set)
    for b in bom_data:
        p = _norm(b.parent_product_id)
        c = _norm(b.child_product_id)
        if p and c:
            G[p].add(c)
            G[c].add(p)
    return G


def connected_component_nodes(G, start):
    start = _norm(start)
    if not start:
        return set()
    seen = set()
    q = deque([start])
    while q:
        u = q.popleft()
        if u in seen:
            continue
        seen.add(u)
        for v in G.get(u, ()):
            if v not in seen:
                q.append(v)
    return seen


def run_grouping_algorithm(all_ofs, bom_data, horizon_H_weeks_param):
    group_counter = 1
    groups = []
    skipped = set()

    def norm(x):
        return ''.join(str(x or '').split()).upper()

    bom_graph = build_bom_graph(bom_data)

    product_level = {}

    for b in bom_data:
        p = norm(b.parent_product_id)
        c = norm(b.child_product_id)

        try:
            c_lvl = int(getattr(b, "child_bom_level", 0) or 0)
        except Exception:
            c_lvl = 0

        try:
            p_lvl = int(getattr(b, "parent_bom_level", 0) or 0)
        except Exception:
            p_lvl = 0

        if c and c_lvl > 0:
            product_level[c] = c_lvl if c not in product_level else max(product_level[c], c_lvl)
        if p and p_lvl > 0:
            product_level[p] = p_lvl if p not in product_level else max(product_level[p], p_lvl)

    for of in all_ofs:
        pid = norm(of.product_id)
        lvl = product_level.get(pid, 0)
        try:
            of.effective_bom_level = int(lvl)
        except Exception:
            of.effective_bom_level = 0

    def get_level(of):
        try:
            return int(getattr(of, "effective_bom_level", 0))
        except Exception:
            return 0

    def first_unassigned_highest_level():
        best_of = None
        best_level = None
        best_date = None
        for of in all_ofs:
            if of.id in skipped:
                continue
            if of.assigned_group_id is not None:
                continue
            lvl = get_level(of)
            if best_of is None or lvl > best_level or (
                lvl == best_level and of.need_date < best_date
            ):
                best_of = of
                best_level = lvl
                best_date = of.need_date
        return best_of

    while True:
        anchor_of = first_unassigned_highest_level()
        if anchor_of is None:
            break

        anchor_pid_norm = norm(anchor_of.product_id)

        family = connected_component_nodes(bom_graph, anchor_of.product_id)
        if not family:
            family = {anchor_pid_norm}

        window_start_date = anchor_of.need_date
        window_end_date = window_start_date + timedelta(weeks=horizon_H_weeks_param) - timedelta(days=1)

        raw_candidates = [
            of
            for of in all_ofs
            if (
                of.assigned_group_id is None
                and window_start_date <= of.need_date <= window_end_date
                and norm(of.product_id) in family
            )
        ]

        cand_pids_raw = {norm(of.product_id) for of in raw_candidates}
        related_pids = set()

        for b in bom_data:
            p = norm(b.parent_product_id)
            c = norm(b.child_product_id)
            if p in cand_pids_raw and c in cand_pids_raw:
                related_pids.add(p)
                related_pids.add(c)

        candidates = [
            of for of in raw_candidates
            if norm(of.product_id) in related_pids
        ]

        if len(candidates) <= 1:
            skipped.add(anchor_of.id)
            continue

        if anchor_of not in candidates:
            skipped.add(anchor_of.id)
            continue

        current_group = Group(
            id=f"GRP{group_counter}",
            ps_product_id=anchor_of.product_id,
            initial_ps_of=anchor_of,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
            initial_ps_as_stock=False,
        )

        def sort_key(of):
            return (-get_level(of), of.need_date, of.product_id)

        for ofx in sorted(candidates, key=sort_key):
            if ofx.id == anchor_of.id:
                continue
            current_group.add_of(ofx, ps_quantity_change=0)

        current_group.calculate_consumption(bom_data)

        groups.append(current_group)
        group_counter += 1

    return groups, all_ofs


def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    import json
    from collections import defaultdict as _dd

    def dt_to_str(dt):
        return dt.strftime("%Y-%m-%d %H:%M") if dt else None

    def days_delay_if_late(scheduled_end_dt, need_dt):
        if scheduled_end_dt is None:
            return 0
        delta = (scheduled_end_dt.date() - need_dt.date()).days
        return delta if delta > 0 else 0

    advance_retreat_weeks = int(params.get("advance_retreat_weeks", 3))
    adv_td = timedelta(weeks=advance_retreat_weeks)

    all_need_dates = [
        of.need_date
        for of in all_ofs_with_groups
        if getattr(of, "need_date", None) is not None
    ]
    if all_need_dates:
        min_need = min(all_need_dates)
        base_monday = (min_need - timedelta(days=min_need.weekday())).date()
        for p in posts_map.values():
            if hasattr(p, "set_week0_monday"):
                p.set_week0_monday(base_monday)

    smoothing_json_path = params.get("smoothing_json_path")
    if not smoothing_json_path:
        uploads = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads, exist_ok=True)
        smoothing_json_path = os.path.join(uploads, "smoothing_view.json")

    smoothing_items = []
    scheduled_ofs = []

    def get_level(of):
        try:
            return int(getattr(of, "effective_bom_level", 0))
        except Exception:
            return 0

    def _norm_code_local(x):
        return "".join(str(x or "").replace("\ufeff", "").split()).upper()

    parent_to_children = _dd(set)
    for b in bom_data:
        p_raw = getattr(b, "parent_product_id", "") or ""
        c_raw = getattr(b, "child_product_id", "") or ""
        p = _norm_code_local(p_raw)
        c = _norm_code_local(c_raw)
        if p and c:
            parent_to_children[p].add(c)

    bom_children = _dd(list)
    for b in bom_data:
        p_raw = getattr(b, "parent_product_id", "") or ""
        c_raw = getattr(b, "child_product_id", "") or ""
        p = _norm_code_local(p_raw)
        c = _norm_code_local(c_raw)
        if p and c:
            try:
                q = float(b.quantity_child_per_parent)
            except Exception:
                q = try_parse_float(getattr(b, "quantity_child_per_parent", 0) or 0)
            bom_children[p].append((c, q))

    def order_group_ofs_by_bom_chain(group_ofs):
        product_to_ofs = _dd(list)
        for of in group_ofs:
            pn = _norm_code_local(of.product_id)
            product_to_ofs[pn].append(of)

        for lst in product_to_ofs.values():
            lst.sort(key=lambda o: (o.need_date, o.id))

        product_level = {}
        for pn, ofs in product_to_ofs.items():
            levels = [get_level(of) for of in ofs]
            product_level[pn] = max(levels) if levels else 0

        products_sorted = sorted(
            product_to_ofs.keys(),
            key=lambda pn: -product_level.get(pn, 0)
        )

        visited_of_ids = set()
        ordered = []

        def dfs_product(pn):
            if pn not in product_to_ofs:
                return
            for of in product_to_ofs[pn]:
                if of.id not in visited_of_ids:
                    ordered.append(of)
                    visited_of_ids.add(of.id)
            for child_pn in parent_to_children.get(pn, set()):
                dfs_product(child_pn)

        for pn in products_sorted:
            dfs_product(pn)

        for of in group_ofs:
            if of.id not in visited_of_ids:
                ordered.append(of)

        return ordered

    def find_first_op_two_phase(post_obj, need_dt, op_hours, group_start_date,
                                min_group_start=None, not_before_dt=None):
        adv_td_local = timedelta(weeks=advance_retreat_weeks)

        g_start = (
            group_start_date
            if isinstance(group_start_date, datetime)
            else datetime.combine(group_start_date, time.min)
        )

        if min_group_start is not None and min_group_start > g_start:
            g_start = min_group_start

        if not_before_dt is not None and not_before_dt > g_start:
            g_start = not_before_dt

        need_d = need_dt.date()
        hi_d = (need_dt + adv_td_local).date()

        a_start = max(g_start, need_dt - adv_td_local)
        if not_before_dt is not None and a_start < not_before_dt:
            a_start = not_before_dt
        a_start = post_obj._get_next_working_datetime(a_start)

        s, e = post_obj.find_available_slot(a_start, op_hours, of_id_to_ignore=None)
        if s and e and s.date() <= need_d and e.date() <= hi_d:
            return s, e

        next_day_midnight = datetime.combine(need_d + timedelta(days=1), time.min)
        b_start = max(next_day_midnight, g_start)
        if not_before_dt is not None and b_start < not_before_dt:
            b_start = not_before_dt
        b_start = post_obj._get_next_working_datetime(b_start)

        if b_start.date() <= hi_d:
            s, e = post_obj.find_available_slot(b_start, op_hours, of_id_to_ignore=None)
            if s and e and (need_d < s.date() <= hi_d) and e.date() <= hi_d:
                return s, e

        return None, None

    for group in sorted(groups, key=lambda g: g.time_window_start):
        group_ofs = [of for of in all_ofs_with_groups if of.assigned_group_id == group.id]

        ofs_sorted = order_group_ofs_by_bom_chain(group_ofs)

        group_products_norm = {_norm_code_local(of.product_id) for of in group_ofs}

        production_lots = _dd(list)

        canonical_norm_to_raw = {}
        for b in bom_data:
            for raw in [
                getattr(b, "parent_product_id", "") or "",
                getattr(b, "child_product_id", "") or "",
            ]:
                pn = _norm_code_local(raw)
                if pn and pn not in canonical_norm_to_raw:
                    canonical_norm_to_raw[pn] = raw

        group_post_last_end = {}

        def compute_stock_feasibility(of_obj):
            p_norm = _norm_code_local(of_obj.product_id)
            qty_parent = float(getattr(of_obj, "quantity", 0) or 0)
            if qty_parent <= 0:
                return True, None, {}, ""

            children = bom_children.get(p_norm, [])
            if not children:
                return True, None, {}, ""

            latest_ready = None
            allocations = {}

            for child_norm, coef in children:
                if child_norm not in group_products_norm:
                    continue

                needed = qty_parent * coef
                if needed <= 0:
                    continue

                lots = sorted(
                    production_lots.get(child_norm, []),
                    key=lambda l: l["end_dt"]
                )
                remaining = needed
                child_ready = None
                tmp_alloc = []
                total_available = 0.0

                for idx, lot in enumerate(lots):
                    free = float(lot.get("qty_free", 0.0) or 0.0)
                    if free <= 0:
                        continue

                    take = min(free, remaining)
                    if take <= 0:
                        continue

                    remaining -= take
                    total_available += take
                    tmp_alloc.append((idx, take))
                    child_ready = lot["end_dt"]

                    if remaining <= 1e-9:
                        break

                if remaining > 1e-9:
                    child_raw = canonical_norm_to_raw.get(child_norm, child_norm)
                    reason = (
                        f"Stock insuffisant pour composant {child_raw}: "
                        f"besoin={needed}, dispo={total_available}"
                    )
                    return False, None, {}, reason

                allocations[child_norm] = tmp_alloc
                if child_ready and (latest_ready is None or child_ready > latest_ready):
                    latest_ready = child_ready

            return True, latest_ready, allocations, ""

        def commit_allocations(allocations):
            for child_norm, uses in allocations.items():
                lots = sorted(
                    production_lots.get(child_norm, []),
                    key=lambda l: l["end_dt"]
                )
                for idx, qty_used in uses:
                    if 0 <= idx < len(lots):
                        lots[idx]["qty_free"] = float(
                            lots[idx].get("qty_free", 0.0) or 0.0
                        ) - qty_used
                production_lots[child_norm] = lots

        for of_to_schedule in ofs_sorted:
            need_dt_for_smoothing = of_to_schedule.need_date
            need_d = need_dt_for_smoothing.date()
            hi_d = (need_dt_for_smoothing + adv_td).date()

            stock_ok, components_ready_dt, allocations, stock_reason = compute_stock_feasibility(
                of_to_schedule
            )
            if not stock_ok:
                status_affiche = "ÉCHOUÉ(stock insuffisant)"
                of_to_schedule.status = status_affiche
                of_to_schedule.scheduled_start_date = None
                of_to_schedule.scheduled_end_date = None
                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": need_dt_for_smoothing.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status_affiche,
                        "retard_jours": 0,
                        "operations": [],
                        "debug": stock_reason,
                    }
                )
                scheduled_ofs.append(of_to_schedule)
                continue

            prod_norm = _norm_code_local(of_to_schedule.product_id)
            children_norms = parent_to_children.get(prod_norm, set())
            if children_norms:
                blocked_by_component_failure = False
                for child_pid_norm in children_norms:
                    child_ofs = [
                        ofc for ofc in group_ofs
                        if _norm_code_local(ofc.product_id) == child_pid_norm
                    ]
                    if child_ofs and all(str(ofc.status).startswith("ÉCHOUÉ") for ofc in child_ofs):
                        blocked_by_component_failure = True
                        break

                if blocked_by_component_failure:
                    status_affiche = "ÉCHOUÉ(stock insuffisant)"
                    of_to_schedule.status = status_affiche
                    of_to_schedule.scheduled_start_date = None
                    of_to_schedule.scheduled_end_date = None
                    smoothing_items.append(
                        {
                            "of_id": of_to_schedule.id,
                            "product_id": of_to_schedule.product_id,
                            "designation": of_to_schedule.designation,
                            "group_id": group.id,
                            "need_date": need_dt_for_smoothing.strftime("%Y-%m-%d"),
                            "scheduled_start": None,
                            "scheduled_end": None,
                            "status": status_affiche,
                            "retard_jours": 0,
                            "operations": [],
                            "debug": "Blocked because component OFs are all ÉCHOUÉ",
                        }
                    )
                    scheduled_ofs.append(of_to_schedule)
                    continue

            key_of = _norm_code_local(of_to_schedule.id)
            key_prod = prod_norm
            key_type = _norm_code_local(of_to_schedule.product_type)

            ops = (
                operations_map.get(key_of, [])
                or operations_map.get(key_prod, [])
                or operations_map.get(key_type, [])
            )

            if not ops:
                status_affiche = "ÉCHOUÉ(poste indispo)"
                of_to_schedule.status = status_affiche
                of_to_schedule.scheduled_start_date = None
                of_to_schedule.scheduled_end_date = None
                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": need_dt_for_smoothing.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status_affiche,
                        "retard_jours": 0,
                        "operations": [],
                        "debug": "No operations",
                    }
                )
                scheduled_ofs.append(of_to_schedule)
                continue

            ops = sorted(ops, key=lambda o: o.sequence)

            for op_def in ops:
                post = posts_map.get(op_def.post_id)
                if post:
                    post.clear_schedule_for_of(of_to_schedule.id + "_" + op_def.operation_name)

            last_end = None
            op_sched = []
            feasible = True
            fail_reason = ""

            for i, op_def in enumerate(ops):
                post = posts_map.get(op_def.post_id)
                if not post:
                    feasible = False
                    fail_reason = f"Missing post {op_def.post_id}"
                    break

                dur_h = op_def.standard_time_hours
                group_last_for_post = group_post_last_end.get(post.id)

                if i == 0:
                    s_dt, e_dt = find_first_op_two_phase(
                        post,
                        need_dt_for_smoothing,
                        dur_h,
                        group.time_window_start,
                        min_group_start=group_last_for_post,
                        not_before_dt=components_ready_dt,
                    )
                else:
                    start_search = post._get_next_working_datetime(last_end)

                    if group_last_for_post is not None and group_last_for_post > start_search:
                        start_search = post._get_next_working_datetime(group_last_for_post)

                    if components_ready_dt is not None and start_search < components_ready_dt:
                        start_search = post._get_next_working_datetime(components_ready_dt)

                    s_dt, e_dt = post.find_available_slot(
                        start_search,
                        dur_h,
                        of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name,
                    )

                    if s_dt and e_dt and e_dt.date() > hi_d:
                        s_dt, e_dt = None, None

                if s_dt and e_dt:
                    op_sched.append((op_def, post, s_dt, e_dt))
                    last_end = e_dt
                    if group_last_for_post is None or e_dt > group_last_for_post:
                        group_post_last_end[post.id] = e_dt
                else:
                    feasible = False
                    if i == 0 and components_ready_dt is not None:
                        fail_reason = (
                            "No slot for first op within horizon after components ready at "
                            f"{components_ready_dt}"
                        )
                    else:
                        fail_reason = (
                            "No slot in allowed windows within horizon"
                            if i == 0
                            else f"No slot for '{op_def.operation_name}' within horizon"
                        )
                    break

            if feasible and op_sched:
                for op_def, post, s_dt, e_dt in op_sched:
                    post.book_slot(s_dt, e_dt, of_to_schedule.id + "_" + op_def.operation_name)

                start_dt = op_sched[0][2]
                end_dt = op_sched[-1][3]
                of_to_schedule.scheduled_start_date = start_dt
                of_to_schedule.scheduled_end_date = end_dt

                start_d = start_dt.date()

                if start_d <= need_d:
                    statut_calc = "OUI"
                elif need_d < start_d <= hi_d:
                    statut_calc = "NON"
                else:
                    statut_calc = "ÉCHOUÉ"

                if statut_calc == "ÉCHOUÉ":
                    statut_affiche = "NON"
                else:
                    statut_affiche = statut_calc

                of_to_schedule.status = statut_affiche

                if statut_affiche == "NON":
                    retard_jours = days_delay_if_late(end_dt, need_dt_for_smoothing)
                else:
                    retard_jours = 0

                commit_allocations(allocations)

                p_norm = _norm_code_local(of_to_schedule.product_id)
                qty = float(getattr(of_to_schedule, "quantity", 0) or 0)
                if qty > 0:
                    production_lots[p_norm].append({"end_dt": end_dt, "qty_free": qty})
                    production_lots[p_norm] = sorted(
                        production_lots[p_norm],
                        key=lambda l: l["end_dt"]
                    )

                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": need_dt_for_smoothing.strftime("%Y-%m-%d"),
                        "scheduled_start": dt_to_str(start_dt),
                        "scheduled_end": dt_to_str(end_dt),
                        "status": statut_affiche,
                        "retard_jours": retard_jours,
                        "operations": [
                            {
                                "operation": d[0].operation_name,
                                "post_id": d[0].post_id,
                                "start": dt_to_str(d[2]),
                                "end": dt_to_str(d[3]),
                            }
                            for d in op_sched
                        ],
                    }
                )
            else:
                status_affiche = "ÉCHOUÉ(poste indispo)"
                of_to_schedule.status = status_affiche
                of_to_schedule.scheduled_start_date = None
                of_to_schedule.scheduled_end_date = None
                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": need_dt_for_smoothing.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status_affiche,
                        "retard_jours": 0,
                        "operations": [],
                        "debug": fail_reason or "No slot",
                    }
                )

            scheduled_ofs.append(of_to_schedule)

    final_by_id = {of.id: of for of in scheduled_ofs}
    updated_all = [final_by_id.get(orig.id, orig) for orig in all_ofs_with_groups]

    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": smoothing_items}
    try:
        with open(smoothing_json_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Smoothing] JSON write error: {e}")

    ops_excel_path = params.get("smoothing_ops_excel_path")
    if ops_excel_path:
        try:
            write_operations_excel_from_smoothing_items(smoothing_items, ops_excel_path)
            print(f"[Smoothing] Operations Excel written to {ops_excel_path}")
        except Exception as e:
            print(f"[Smoothing] Excel ops write error: {e}")
    
    weekly_capacity_report_path = params.get("weekly_capacity_report_path")
    if weekly_capacity_report_path:
        try:
            write_posts_weekly_capacity_report(posts_map, weekly_capacity_report_path)
            print(f"[Smoothing] Weekly capacity report written to {weekly_capacity_report_path}")
        except Exception as e:
            print(f"[Smoothing] Weekly capacity report error: {e}")

    return updated_all


def write_grouped_needs_to_file(filepath, grouped_list_data, all_ofs_scheduled):
    from collections import defaultdict

    print(f"\nWriting grouped needs to {filepath}")

    output_header = [
        "Part",
        "Description",
        "Order Code",
        "FG",
        "CAT",
        "US",
        "FS",
        "Qty",
        "X3 Date",
        "GRP_FLG",
        "Start Date",
        "Delay",
        "Stock_Produit",
    ]

    def get_bom_level(of_obj):
        try:
            return int(getattr(of_obj, "effective_bom_level", 0))
        except Exception:
            return 0

    def _norm(x: str) -> str:
        return "".join(str(x or "").replace("\ufeff", "").split()).upper()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(output_header)

        processed_of_ids_in_groups = set()

        def extract_group_number(group):
            try:
                return int(group.id.replace("GRP", ""))
            except Exception:
                return 0

        for group in sorted(grouped_list_data, key=extract_group_number):
            f.write(f"\n# Group ID: {group.id}\n")
            f.write(f"#   Produit PS Principal (ancre): {group.ps_product_id}\n")
            f.write(
                f"#   Fenêtre Temporelle: "
                f"{group.time_window_start.strftime('%Y-%m-%d')} à "
                f"{group.time_window_end.strftime('%Y-%m-%d')}\n"
            )

            product_norm_to_raw = {}

            ofs_in_group = [of for of in all_ofs_scheduled if of.assigned_group_id == group.id]
            for of in ofs_in_group:
                pn = _norm(of.product_id)
                if pn and pn not in product_norm_to_raw:
                    product_norm_to_raw[pn] = of.product_id

            if hasattr(group, "individual_product_stocks") and group.ps_product_id in group.individual_product_stocks:
                f.write(
                    f"#   Stock PS Calculé: "
                    f"{group.individual_product_stocks[group.ps_product_id]}\n"
                )
            else:
                f.write("#   Stock PS: Non calculé / Ancre composant\n")

            product_totals = defaultdict(lambda: {"demande": 0.0, "produit": 0.0})

            for of in ofs_in_group:
                pn = _norm(of.product_id)
                q_dem = float(getattr(of, "quantity", 0) or 0)
                q_prod = float(getattr(of, "individual_product_stock", 0.0) or 0.0)
                product_totals[pn]["demande"] += q_dem
                product_totals[pn]["produit"] += q_prod

            pf_norms = sorted(
                {_norm(of.product_id) for of in ofs_in_group if getattr(of, "product_type", "") == "PF"}
            )

            f.write("#   PF produits dans le groupe (quantité produite vs demandée):\n")
            if not pf_norms:
                f.write("#     Aucun PF dans ce groupe.\n")
            else:
                for pn in pf_norms:
                    raw = product_norm_to_raw.get(pn, pn)
                    dem = product_totals[pn]["demande"]
                    prod = product_totals[pn]["produit"]
                    f.write(f"#     - {raw}: produit={prod}, demandé={dem}\n")

            f.write("#   Stock net restant dans le groupe (production - consommation):\n")
            if hasattr(group, "component_stocks") and group.component_stocks:
                for pn in sorted(group.component_stocks.keys()):
                    stock_val = group.component_stocks.get(pn, 0.0)
                    raw = product_norm_to_raw.get(pn, pn)
                    f.write(f"#     - {raw}: {stock_val}\n")
            else:
                f.write("#     Stock non calculé.\n")

            ofs_in_group_sorted = sorted(
                ofs_in_group,
                key=lambda x: (get_bom_level(x), x.need_date, x.product_id),
            )

            for of_obj in ofs_in_group_sorted:
                desc_parts = of_obj.designation.split()
                if not desc_parts:
                    processed_description = ""
                elif len(desc_parts) >= 2 and desc_parts[0].upper() == "BATENS":
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"
                elif len(desc_parts) == 1:
                    processed_description = desc_parts[0]
                else:
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"

                processed_order_code = of_obj.id
                grp_flg = (
                    of_obj.assigned_group_id.replace("GRP", "")
                    if of_obj.assigned_group_id
                    else ""
                )
                start_date_str = (
                    of_obj.scheduled_start_date.strftime("%Y-%m-%d")
                    if of_obj.scheduled_start_date
                    else ""
                )
                delay_val = "0"
                if getattr(of_obj, "status", "") == "NON" and of_obj.scheduled_end_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_end_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))

                stock_val = getattr(of_obj, "individual_product_stock", None)
                if stock_val is None:
                    stock_val = getattr(of_obj, "remaining_stock", None)
                if stock_val is None:
                    stock_val = float(getattr(of_obj, "quantity", 0.0) or 0.0)

                writer.writerow(
                    [
                        of_obj.product_id,
                        processed_description,
                        processed_order_code,
                        of_obj.fg,
                        of_obj.cat,
                        of_obj.us,
                        of_obj.fs,
                        of_obj.quantity,
                        of_obj.need_date.strftime("%Y-%m-%d")
                        if of_obj.need_date
                        else "",
                        grp_flg,
                        start_date_str,
                        delay_val,
                        stock_val,
                    ]
                )
                processed_of_ids_in_groups.add(of_obj.id)

        f.write("\n# OFs Non Affectés:\n")
        unassigned = [of for of in all_ofs_scheduled if of.id not in processed_of_ids_in_groups]

        unassigned_sorted = sorted(
            unassigned,
            key=lambda x: (get_bom_level(x), x.need_date, x.id),
        )

        for of_obj in unassigned_sorted:
            desc_parts = of_obj.designation.split()
            if not desc_parts:
                processed_description = ""
            elif len(desc_parts) >= 2 and desc_parts[0].upper() == "BATENS":
                processed_description = f"{desc_parts[0]} {desc_parts[1]}"
            elif len(desc_parts) == 1:
                processed_description = desc_parts[0]
            else:
                processed_description = f"{desc_parts[0]} {desc_parts[1]}"

            processed_order_code = of_obj.id[:10]
            grp_flg = (
                of_obj.assigned_group_id.replace("GRP", "")
                if of_obj.assigned_group_id
                else ""
            )
            start_date_str = (
                of_obj.scheduled_start_date.strftime("%Y-%m-%d")
                if of_obj.scheduled_start_date
                else ""
            )
            delay_val = "0"
            if getattr(of_obj, "status", "") == "NON" and of_obj.scheduled_end_date and of_obj.need_date:
                delay_days = (of_obj.scheduled_end_date - of_obj.need_date).days
                delay_val = str(max(0, delay_days))

            stock_val = getattr(of_obj, "individual_product_stock", None)
            if stock_val is None:
                stock_val = getattr(of_obj, "remaining_stock", None)
            if stock_val is None:
                stock_val = float(getattr(of_obj, "quantity", 0.0) or 0.0)

            writer.writerow(
                [
                    of_obj.product_id,
                    processed_description,
                    processed_order_code,
                    of_obj.fg,
                    of_obj.cat,
                    of_obj.us,
                    of_obj.fs,
                    int(of_obj.quantity),
                    of_obj.need_date.strftime("%Y-%m-%d")
                    if of_obj.need_date
                    else "",
                    grp_flg,
                    start_date_str,
                    delay_val,
                    stock_val,
                ]
            )

    print(f"Output written to {filepath}.")


def write_smoothing_view_json(items, json_path):
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": items}
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        import json as _json

        _json.dump(payload, f, ensure_ascii=False, indent=2)


def write_operations_excel_from_smoothing_items(smoothing_items, output_filepath):
    import csv
    import os

    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

    header = ["OF", "Poste", "Date Début", "Date Fin"]

    with open(output_filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)

        for item in smoothing_items:
            of_id = item.get("of_id", "")
            for op in item.get("operations", []):
                writer.writerow([
                    of_id,
                    op.get("post_id", ""),
                    op.get("start", ""),
                    op.get("end", ""),
                ])


def load_ofs_from_file(filepath):
    print(f"Loading OFs from {filepath}")
    ofs = []

    ALIASES = {
        "date": ["date", "x3 date", "xdate", "need date", "required date", "delivery date"],
        "part": ["part", "code article", "product id", "id produit", "article"],
        "description": ["description", "libelle", "label"],
        "order code": ["order code", "of", "order", "work order", "code of", "ordercode"],
        "fg": ["fg"],
        "cat us fs": ["cat us fs", "cat/us/fs", "cat_us_fs", "catusfs"],
        "qty": ["qty", "quantite", "quantity", "qte"],
    }

    required = ["Part", "Description", "Order Code", "FG", "CAT US FS", "Qty", "Date"]

    def _alias_map(fieldnames):
        lower = {c.strip().lower(): c.strip() for c in (fieldnames or [])}
        out = {}
        for want in required:
            keys = [want] + ALIASES.get(want.lower(), [])
            hit = None
            for k in keys:
                if k.lower() in lower:
                    hit = lower[k.lower()]
                    break
            if not hit:
                return None
            out[want] = hit
        return out

    f, reader, used_delim, used_enc = _make_reader(
        filepath, required_cols=None, fallback="\t"
    )
    if not reader or not reader.fieldnames:
        print(f"Warning: CSV file {filepath} appears empty or header missing.")
        if f:
            f.close()
        return []

    mapped_cols = _alias_map(reader.fieldnames)
    if not mapped_cols:
        if f:
            f.close()
        raise ValueError(
            f"CSV file {filepath} missing required columns: {['Date']}. "
            f"Found: {reader.fieldnames}"
        )

    try:
        for row_num, row in enumerate(reader, 1):
            try:
                part_val = row[mapped_cols["Part"]]
                if part_val.startswith("PF"):
                    product_type_derived = "PF"
                elif part_val.startswith("SF"):
                    product_type_derived = "SF"
                elif part_val.startswith("PS"):
                    product_type_derived = "PS"
                else:
                    product_type_derived = "UNKNOWN"

                cat_us_fs_raw = (row.get(mapped_cols["CAT US FS"], "") or "").strip()
                cat_us_fs_parts = cat_us_fs_raw.split()
                cat_val, us_val, fs_val = "", "1", "1"
                if len(cat_us_fs_parts) == 3:
                    cat_val, us_val, fs_val = cat_us_fs_parts
                elif len(cat_us_fs_parts) == 1:
                    cat_val = cat_us_fs_parts[0]
                elif len(cat_us_fs_parts) > 0:
                    cat_val = cat_us_fs_parts[0]

                bom_level_derived = 0

                of = ManufacturingOrder(
                    id=row[mapped_cols["Order Code"]],
                    designation=row[mapped_cols["Description"]],
                    product_id=part_val,
                    product_type=product_type_derived,
                    bom_level=bom_level_derived,
                    need_date_str=row[mapped_cols["Date"]],
                    quantity=row[mapped_cols["Qty"]],
                    fg=row[mapped_cols["FG"]],
                    cat=cat_val,
                    us=us_val,
                    fs=fs_val,
                )
                ofs.append(of)
            except Exception as e:
                print(f"Row {row_num} error: {e}")
    finally:
        if f:
            f.close()

    print(f"Loaded {len(ofs)} OFs (delimiter='{used_delim}', encoding='{used_enc}').")
    return ofs


def load_bom_from_file(filepath):
    print(f"Loading BOM from {filepath}")
    bom_entries = []

    required_cols = [
        "ParentProductID",
        "ChildProductID",
        "QuantityChildPerParent",
        "ChildBOMLevel",
    ]

    aliases = {
        "ParentProductID": ["parentproductid", "parent", "parent id", "id parent"],
        "ChildProductID": ["childproductid", "child", "child id", "id child"],
        "QuantityChildPerParent": [
            "quantitychildperparent",
            "qty/parent",
            "qty_per_parent",
            "qte/parent",
        ],
        "ChildBOMLevel": ["childbomlevel", "child level", "niveau enfant", "level"],
        "ParentBOMLevel": ["parentbomlevel", "parent level", "niveau parent"],
    }

    def _alias_map(fieldnames):
        lower = {c.strip().lower(): c.strip() for c in fieldnames}
        out = {}
        for want in required_cols:
            keys = [want] + aliases.get(want, [])
            hit = None
            for k in keys:
                if k.lower() in lower:
                    hit = lower[k.lower()]
                    break
            if not hit:
                return None
            out[want] = hit
        return out

    f, reader, used_delim, used_enc = _make_reader(
        filepath, required_cols=None, fallback=","
    )
    if not reader or not reader.fieldnames:
        print(f"Error: BOM file not found at {filepath}. Returning empty list.")
        if f:
            f.close()
        return []

    map_cols = _alias_map(reader.fieldnames)
    if not map_cols:
        print(
            f"Error loading BOM from {filepath}: missing required columns. "
            f"Found: {reader.fieldnames}. Returning empty list."
        )
        if f:
            f.close()
        return []

    lower_fields = {c.strip().lower(): c.strip() for c in reader.fieldnames}
    parent_level_col = None
    for k in ["ParentBOMLevel"] + aliases.get("ParentBOMLevel", []):
        if k.lower() in lower_fields:
            parent_level_col = lower_fields[k.lower()]
            break

    try:
        for row_num, row in enumerate(reader, 1):
            try:
                parent_lvl_val = row[parent_level_col] if parent_level_col else None

                entry = BOMEntry(
                    parent_product_id=row[map_cols["ParentProductID"]],
                    child_product_id=row[map_cols["ChildProductID"]],
                    quantity_child_per_parent=row[map_cols["QuantityChildPerParent"]],
                    child_bom_level=row[map_cols["ChildBOMLevel"]],
                    parent_bom_level=parent_lvl_val,
                )
                bom_entries.append(entry)
            except Exception as e:
                print(f"BOM row {row_num} error: {e}")
    finally:
        if f:
            f.close()

    print(f"Loaded {len(bom_entries)} BOM entries (delimiter='{used_delim}', encoding='{used_enc}').")
    return bom_entries


def load_posts_and_operations_data(filepath_posts, filepath_post_unavailability, filepath_operations):
    print(
        f"Loading Posts, Unavailability & Operations from "
        f"{filepath_posts}, {filepath_post_unavailability}, {filepath_operations}"
    )

    posts_map = {}

    try:
        required_cols_posts = ["PostID", "PostName", "DefaultCapacityHoursWeek"]

        f_posts, reader_posts, used_delim_posts, used_enc_posts = _make_reader(
            filepath_posts,
            required_cols=None,
            fallback=",",
        )

        if not reader_posts or not reader_posts.fieldnames:
            raise FileNotFoundError(
                f"Posts CSV {filepath_posts} appears empty or has no header."
            )

        lower = {c.strip().lower(): c.strip() for c in reader_posts.fieldnames}
        colmap_posts = {}
        for col in required_cols_posts:
            if col.lower() in lower:
                colmap_posts[col] = lower[col.lower()]
            else:
                raise ValueError(
                    f"Posts CSV {filepath_posts} missing required column '{col}'. "
                    f"Found: {reader_posts.fieldnames}"
                )

        week_cols = {}
        for col in reader_posts.fieldnames:
            key_norm = col.strip().lower().replace(" ", "")
            m = re.match(r"week(\d+)", key_norm)
            if m:
                week_index = int(m.group(1))
                week_cols[week_index] = col.strip()

        for row in reader_posts:
            raw_pid = row[colmap_posts["PostID"]]
            pid = norm_code(raw_pid)

            try:
                default_week_capacity = float(
                    try_parse_float(row[colmap_posts["DefaultCapacityHoursWeek"]])
                )
            except Exception:
                default_week_capacity = float(POST_DEFAULT_CAPACITY_HOURS_WEEK)

            weekly_capacity_by_week = {}
            for wk_index, colname in week_cols.items():
                raw_val = row.get(colname, "")
                if raw_val is None:
                    continue
                txt = str(raw_val).strip()
                if not txt:
                    continue
                try:
                    weekly_capacity_by_week[wk_index] = float(try_parse_float(txt))
                except Exception:
                    continue

            post = Post(
                id=pid,
                name=row[colmap_posts["PostName"]],
                default_capacity_hours_week=default_week_capacity,
                weekly_capacity_by_week=weekly_capacity_by_week,
            )
            posts_map[post.id] = post

        if f_posts:
            f_posts.close()

        print(
            f"Loaded {len(posts_map)} posts from {filepath_posts} "
            f"(delimiter='{used_delim_posts}', encoding='{used_enc_posts}')."
        )

    except FileNotFoundError:
        print(f"Warning: Posts file not found at {filepath_posts}. Using empty posts_map.")
    except Exception as e:
        print(f"Error loading Posts from {filepath_posts}: {e}")

    try:
        if filepath_post_unavailability and os.path.isfile(filepath_post_unavailability):
            f_unav, reader_unav, used_delim_unav, used_enc_unav = _make_reader(
                filepath_post_unavailability,
                required_cols=None,
                fallback=",",
            )
            if reader_unav and reader_unav.fieldnames:
                required_cols_unavail = ["PostID", "UnavailableStartDate", "UnavailableEndDate"]
                lower_u = {c.strip().lower(): c.strip() for c in reader_unav.fieldnames}
                colmap_unav = {}
                ok = True
                for col in required_cols_unavail:
                    if col.lower() in lower_u:
                        colmap_unav[col] = lower_u[col.lower()]
                    else:
                        ok = False
                        break
                if ok:
                    for row in reader_unav:
                        raw_pid = row.get(colmap_unav["PostID"], "")
                        pid = norm_code(raw_pid)
                        if (
                            pid in posts_map
                            and row.get(colmap_unav["UnavailableStartDate"])
                            and row.get(colmap_unav["UnavailableEndDate"])
                        ):
                            posts_map[pid].add_unavailable_period(
                                row[colmap_unav["UnavailableStartDate"]],
                                row[colmap_unav["UnavailableEndDate"]],
                            )
                if f_unav:
                    f_unav.close()
    except Exception as e:
        print(f"Warning: Failed reading unavailability file {filepath_post_unavailability}: {e}.")

    operations_map = defaultdict(list)
    try:
        f_ops, reader_ops, used_delim_ops, used_enc_ops = _make_reader(
            filepath_operations,
            required_cols=None,
            fallback=",",
        )

        if not reader_ops or not reader_ops.fieldnames:
            raise FileNotFoundError(
                f"Operations file {filepath_operations} appears empty or has no header."
            )

        aliases_ops = {
            "ProductID": ["productid", "product id", "ofid"],
            "OperationName": ["operationname", "operation", "opname"],
            "PostID": ["postid", "poste", "post id"],
            "StandardTimeHours": ["standardtimehours", "stdtime", "duree", "duration"],
            "Sequence": ["sequence", "seq", "ordre"],
            "Priority": ["priority", "priorite"],
        }

        lower_ops = {c.strip().lower(): c.strip() for c in reader_ops.fieldnames}
        colmap_ops = {}

        for wanted, alts in aliases_ops.items():
            keys = [wanted] + alts
            hit = None
            for k in keys:
                if k.lower() in lower_ops:
                    hit = lower_ops[k.lower()]
                    break
            if not hit:
                raise ValueError(
                    f"Column '{wanted}' not found in operations file. Found: {reader_ops.fieldnames}"
                )
            colmap_ops[wanted] = hit

        for row in reader_ops:
            raw_key = row.get(colmap_ops["ProductID"]) or row.get("ProductType") or "UNKNOWN_OP_KEY"
            key = norm_code(raw_key)
            if key == "UNKNOWN_OP_KEY" or not key:
                continue

            raw_post_id = row.get(colmap_ops["PostID"], "")
            post_id_norm = norm_code(raw_post_id)

            seq_str = row.get(colmap_ops["Sequence"], "0") or "0"
            pri_str = row.get(colmap_ops["Priority"], "1") or "1"

            op = Operation(
                product_key=key,
                operation_name=row[colmap_ops["OperationName"]],
                post_id=post_id_norm,
                standard_time_hours=row[colmap_ops["StandardTimeHours"]],
                sequence=int(seq_str),
                priority=int(pri_str),
            )
            operations_map[key].append(op)

        if f_ops:
            f_ops.close()

    except FileNotFoundError:
        print(f"Warning: Operations file not found at {filepath_operations}.")
    except Exception as e:
        print(f"Error loading Operations from {filepath_operations}: {e}")

    print(
        f"Loaded {len(posts_map)} posts and "
        f"{sum(len(ops) for ops in operations_map.values())} operation rules."
    )
    return posts_map, operations_map


def load_compact_input_file(filepath):
    ofs_list = []
    bom_list = []
    last_err = None

    for enc in ENCODING_CANDIDATES:
        try:
            with open(filepath, "r", encoding=enc) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = None
                    for d in ["\t", ";", ",", "|", ":", "^"]:
                        tmp = line.split(d)
                        if len(tmp) > 1:
                            parts = tmp
                            break
                    if parts is None:
                        parts = [p for p in line.split() if p]
                    tag = parts[0].upper()
                    if tag == "OFS":
                        _, of_id, designation, product_id, fg, cat, us, fs, qty, need_date = parts[:10]
                        if product_id.startswith("PF"):
                            product_type = "PF"
                        elif product_id.startswith("SF"):
                            product_type = "SF"
                        elif product_id.startswith("PS"):
                            product_type = "PS"
                        else:
                            product_type = "UNKNOWN"
                        try:
                            bom_level = int(cat) if cat else 0
                        except ValueError:
                            bom_level = 0
                        ofs_list.append(
                            ManufacturingOrder(
                                id=of_id,
                                designation=designation,
                                product_id=product_id,
                                product_type=product_type,
                                bom_level=bom_level,
                                need_date_str=need_date,
                                quantity=qty,
                                fg=fg,
                                cat=cat,
                                us=us,
                                fs=fs,
                            )
                        )
                    elif tag == "BOM":
                        if len(parts) >= 6:
                            _, parent, child, qty_per_parent, child_level, parent_level = parts[:6]
                        else:
                            _, parent, child, qty_per_parent, child_level = parts[:5]
                            parent_level = None
                        bom_list.append(
                            BOMEntry(
                                parent_product_id=parent,
                                child_product_id=child,
                                quantity_child_per_parent=qty_per_parent,
                                child_bom_level=child_level,
                                parent_bom_level=parent_level,
                            )
                        )
            return ofs_list, bom_list
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            break

    if last_err:
        print(f"Erreur lecture compact '{filepath}': {last_err}")
    return ofs_list, bom_list


def write_posts_weekly_capacity_report(posts_map, output_filepath):
    """Rapport capacité/charge par poste et par semaine."""
    import csv
    import os
    from datetime import datetime, timedelta, time

    folder = os.path.dirname(output_filepath)
    if folder:
        os.makedirs(folder, exist_ok=True)

    header = [
        "PostID",
        "PostName",
        "WeekIndex",
        "WeekStartDate",
        "WeekEndDate",
        "AllowedHours",
        "PlannedHours",
        "DeltaHours",
        "RespectCapacity",
    ]

    with open(output_filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)

        for post in posts_map.values():
            base = getattr(post, "planning_start_monday", None)
            if base is None:
                continue

            for wk_index, planned in sorted(post.weekly_load_hours.items()):
                week_start = base + timedelta(days=7 * (wk_index - 1))
                week_end = week_start + timedelta(days=6)

                dt_for_wk = datetime.combine(week_start, time.min)
                allowed = float(post._allowed_hours_for_week(dt_for_wk))

                delta = allowed - float(planned)
                respect = "OUI" if planned <= allowed + 1e-6 else "NON"

                writer.writerow([
                    post.id,
                    post.name,
                    wk_index,
                    week_start.strftime("%Y-%m-%d"),
                    week_end.strftime("%Y-%m-%d"),
                    round(allowed, 2),
                    round(planned, 2),
                    round(delta, 2),
                    respect,
                ])


if __name__ == "__main__":
    compact_file = "input_compact.txt"
    ofs_file = "test_besoins.csv"
    bom_file = "test_nomenclature_client.csv"
    posts_file = "test_posts_client.csv"
    post_unavailability_file = ""
    operations_file = "test_operations_client.csv"
    output_file = "test_besoins_groupes_output.txt"

    if os.path.exists(compact_file):
        print(f"Mode compact : {compact_file}")
        all_ofs, bom_data = load_compact_input_file(compact_file)
    else:
        print("Mode CSV.")
        all_ofs = load_ofs_from_file(ofs_file)
        bom_data = load_bom_from_file(bom_file)

    posts_map, operations_map = load_posts_and_operations_data(
        posts_file,
        post_unavailability_file,
        operations_file
    )

    print(f"[DEBUG] Nb posts: {len(posts_map)}")
    print(f"[DEBUG] Nb clés opérations: {len(operations_map)}")
    print(f"[DEBUG] Exemple clés opérations: {list(operations_map.keys())[:10]}")

    params = {
        "advance_retreat_weeks": ADVANCE_RETREAT_WEEKS,
        # "smoothing_json_path": "uploads/smoothing_view.json",
        # "smoothing_ops_excel_path": "uploads/smoothing_ops.csv",
        "weekly_capacity_report_path": "uploads/weekly_capacity_report.csv",
    }

    groups, all_ofs_with_groups = run_grouping_algorithm(
        all_ofs,
        bom_data,
        HORIZON_H_WEEKS
    )

    all_ofs_scheduled = smooth_and_schedule_groups(
        groups,
        all_ofs_with_groups,
        bom_data,
        posts_map,
        operations_map,
        params
    )

    write_grouped_needs_to_file(output_file, groups, all_ofs_scheduled)
    print(f"\nDone -> {output_file}")
