from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import calendar
import csv
import os
import re
import json
from functools import lru_cache

# ============================================================================
# CONSTANTS
# ============================================================================

HORIZON_H_MONTHS = 2
HORIZON_H_WEEKS = 10
ADVANCE_RETREAT_WEEKS = 3          
ENCODING_CANDIDATES = ("utf-8-sig", "cp1252", "latin-1", "utf-8")

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def norm_code(x: str) -> str:
    if x is None:
        return ""
    s = str(x).replace("\ufeff", "")
    s = "".join(s.split())
    return s.upper()


def detect_csv_delimiter(filepath, fallback=",", sample_size=65536):
    candidates = [b"\t", b";", b"|", b",", b":", b"^"]
    try:
        with open(filepath, "rb") as f:
            sample = f.read(sample_size)
    except (FileNotFoundError, Exception):
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
            return winner.decode("ascii") if isinstance(winner, bytes) else winner
    except Exception:
        pass

    winner = max(counts.items(), key=lambda kv: kv[1])[0]
    return winner.decode("ascii") if isinstance(winner, bytes) else winner


def _make_reader(filepath, required_cols=None, fallback=","):
    delim = detect_csv_delimiter(filepath, fallback=fallback)
    last_err = None
    for enc in ENCODING_CANDIDATES:
        try:
            f = open(filepath, "r", encoding=enc, newline="")
            reader = csv.DictReader(f, delimiter=delim)
            cols = reader.fieldnames
            if not cols:
                f.close()
                continue
            return f, reader, delim, enc
        except FileNotFoundError:
            return None, None, fallback, None
        except (UnicodeDecodeError, Exception) as e:
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
    sanitized = text.replace("\u00a0", "").replace(" ", "")
    if sanitized.count(",") > 0 and sanitized.count(".") > 0:
        sanitized = sanitized.replace(".", "")
    sanitized = sanitized.replace(",", ".")
    return float(sanitized)


def _norm(x: str) -> str:
    """Simple normalization used in many places."""
    return "".join(str(x or "").split()).upper()


# ============================================================================
# CACHED BOM FUNCTIONS
# ============================================================================

@lru_cache(maxsize=None)
def find_qty_of_component_in_product_cached(product_to_make_id, component_to_find_id, bom_tuple):
    """
    Cached version that expects BOM data as a tuple of tuples (parent, child, qty)
    for hashability. This replaces the recursive function with memoization.
    """
    if product_to_make_id == component_to_find_id:
        return 1.0
    total = 0.0
    for parent, child, qty in bom_tuple:
        if parent == product_to_make_id:
            total += qty * find_qty_of_component_in_product_cached(child, component_to_find_id, bom_tuple)
    return total


def prepare_bom_tuple(bom_data):
    """Convert BOM list to a tuple of tuples for caching."""
    return tuple((b.parent_product_id, b.child_product_id, b.quantity_child_per_parent) for b in bom_data)


# ============================================================================
# CLASSES
# ============================================================================

class ManufacturingOrder:
    __slots__ = (
        'id', 'designation', 'product_id', 'raw_product_id', 'product_type',
        'bom_level', 'need_date', 'source_qty', 'quantity', 'unit',
        'horizon_weeks', 'retard_weeks', 'advance_weeks',
        'assigned_group_id', 'status',
        'scheduled_start_date', 'scheduled_end_date', 'fg', 'cat', 'us', 'fs',
        'individual_product_stock', 'effective_bom_level', 'normalized_id', 'normalized_product'
    )

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
        horizon_weeks=None,
        retard_weeks=None,
        advance_weeks=None,
        unit="U",
        status="UNASSIGNED",
    ):
        self.id = id
        self.designation = designation
        self.raw_product_id = product_id
        self.product_id = _norm(product_id)   
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

        self.horizon_weeks = None
        if horizon_weeks not in (None, ""):
            try:
                self.horizon_weeks = int(try_parse_float(horizon_weeks))
            except Exception:
                self.horizon_weeks = None

        self.retard_weeks = None
        if retard_weeks not in (None, ""):
            try:
                self.retard_weeks = int(try_parse_float(retard_weeks))
            except Exception:
                self.retard_weeks = None

        self.advance_weeks = None
        if advance_weeks not in (None, ""):
            try:
                self.advance_weeks = int(try_parse_float(advance_weeks))
            except Exception:
                self.advance_weeks = None

        self.assigned_group_id = None
        self.status = "UNASSIGNED"
        self.scheduled_start_date = None
        self.scheduled_end_date = None

        self.fg = fg
        self.cat = cat
        self.us = us
        self.fs = fs

        self.individual_product_stock = 0.0
        self.effective_bom_level = self.bom_level   

        # Pre-normalized keys for faster lookups
        self.normalized_id = _norm(self.id)
        self.normalized_product = self.product_id   

    def __repr__(self):
        lvl = getattr(self, "effective_bom_level", self.bom_level)
        return (
            f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.raw_product_id}', "
            f"type='{self.product_type}', level={lvl}, "
            f"need={self.need_date.strftime('%Y-%m-%d')}, qty={self.quantity}, "
            f"fg='{self.fg}', cat='{self.cat}', indiv_stock={self.individual_product_stock}, "
            f"group={self.assigned_group_id}, status='{self.status}')"
        )


class BOMEntry:
    __slots__ = ('parent_product_id', 'child_product_id', 'quantity_child_per_parent',
                 'child_bom_level', 'parent_bom_level', 'raw_parent', 'raw_child')

    def __init__(
        self,
        parent_product_id,
        child_product_id,
        quantity_child_per_parent,
        child_bom_level,
        parent_bom_level=None,
    ):
        self.raw_parent = parent_product_id
        self.raw_child = child_product_id
        self.parent_product_id = _norm(parent_product_id)
        self.child_product_id = _norm(child_product_id)
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
            f"BOM(parent='{self.raw_parent}' uses "
            f"{self.quantity_child_per_parent} of child='{self.raw_child}' "
            f"(child_lvl={self.child_bom_level}, parent_lvl={self.parent_bom_level}))"
        )


class Group:
    __slots__ = (
        'id', 'ps_product_id', 'raw_ps_product_id', 'time_window_start', 'time_window_end',
        'ofs', 'current_ps_stock_available', 'component_stocks', 'individual_product_stocks',
        'product_consumption', 'ofs_by_id', 'ofs_by_product'
    )

    def __init__(
        self,
        id,
        ps_product_id,
        initial_ps_of,
        window_start_date,
        window_end_date,
        initial_ps_as_stock=False,
    ):
        self.id = id
        self.raw_ps_product_id = ps_product_id
        self.ps_product_id = _norm(ps_product_id)
        self.time_window_start = window_start_date
        self.time_window_end = window_end_date

        self.ofs = []
        self.ofs_by_id = {}
        self.ofs_by_product = defaultdict(list)
        self.current_ps_stock_available = 0

        self.component_stocks = defaultdict(float)
        self.individual_product_stocks = defaultdict(float)
        self.product_consumption = defaultdict(float)

        ps_q = initial_ps_of.quantity if initial_ps_as_stock else 0
        self.add_of(initial_ps_of, ps_quantity_change=ps_q)

    def add_of(self, of_to_add, ps_quantity_change=0):
        self.ofs.append(of_to_add)
        self.ofs_by_id[of_to_add.id] = of_to_add
        self.ofs_by_product[of_to_add.product_id].append(of_to_add)

        self.current_ps_stock_available += ps_quantity_change
        self.component_stocks[of_to_add.product_id] += ps_quantity_change
        # ensure keys exist
        self.individual_product_stocks[of_to_add.product_id]  
        self.product_consumption[of_to_add.product_id]        

        of_to_add.individual_product_stock = 0.0
        of_to_add.assigned_group_id = self.id
        of_to_add.status = "ASSIGNED"

    def calculate_consumption(self, bom_data):
        if not self.ofs:
            self.component_stocks.clear()
            self.individual_product_stocks.clear()
            self.product_consumption.clear()
            return

        # Precompute product levels from BOM (using normalized IDs)
        product_level = {}
        for bom in bom_data:
            p = bom.parent_product_id
            c = bom.child_product_id
            cl = bom.child_bom_level
            pl = bom.parent_bom_level
            if c and cl > 0:
                product_level[c] = max(product_level.get(c, 0), cl)
            if p and pl > 0:
                product_level[p] = max(product_level.get(p, 0), pl)

        # Produced quantities per product
        produced_qty = defaultdict(float)
        for of in self.ofs:
            produced_qty[of.product_id] += of.quantity

        if not produced_qty:
            self._clear_and_reset()
            return

        # Ensure all produced products have a level (default 0)
        for pid in produced_qty:
            if pid not in product_level:
                product_level[pid] = 0

        levels = set(product_level[pid] for pid in produced_qty)
        max_level = max(levels) if levels else 0
        min_level = min(levels) if levels else 0

        # Build parent->children map only for products that are produced
        bom_by_parent = defaultdict(list)
        for bom in bom_data:
            p = bom.parent_product_id
            if p in produced_qty:
                bom_by_parent[p].append((bom.child_product_id, bom.quantity_child_per_parent))

        product_stock = defaultdict(float)
        product_consumption = defaultdict(float)

        # Process levels descending
        for lvl in range(max_level, min_level - 1, -1):
            for pid, plvl in product_level.items():
                if plvl != lvl or pid not in produced_qty:
                    continue
                qty_prod = produced_qty[pid]
                if qty_prod <= 0:
                    continue
                product_stock[pid] += qty_prod
                for child_id, q_child in bom_by_parent.get(pid, []):
                    need = qty_prod * q_child
                    product_stock[child_id] -= need
                    product_consumption[child_id] += need

        # Distribute remaining stock to individual OFs
        remaining_per_of = {of.id: 0.0 for of in self.ofs}
        for prod_norm in produced_qty:
            stock_left = max(0.0, product_stock.get(prod_norm, 0.0))
            ofs_same = self.ofs_by_product.get(prod_norm, [])
            ofs_sorted = sorted(ofs_same, key=lambda o: (o.need_date, o.id))
            for of in ofs_sorted:
                if stock_left <= 0:
                    break
                assign = min(stock_left, of.quantity)
                remaining_per_of[of.id] = assign
                stock_left -= assign

        for of in self.ofs:
            of.individual_product_stock = max(0.0, remaining_per_of.get(of.id, 0.0))

        self.product_consumption = dict(product_consumption)
        self.component_stocks = dict(product_stock)

        # Update individual product stocks summary
        self.individual_product_stocks = {
            pid: sum(of.individual_product_stock for of in self.ofs_by_product.get(pid, []))
            for pid in produced_qty
        }

    def _clear_and_reset(self):
        self.component_stocks.clear()
        self.individual_product_stocks.clear()
        self.product_consumption.clear()
        for of in self.ofs:
            of.individual_product_stock = 0.0


class Post:
    __slots__ = (
        'id', 'name', 'is_bottleneck', 'work_start_time', 'work_end_time',
        'lunch_start_time', 'lunch_end_time', 'daily_capacity_hours',
        'weekly_capacity_by_week', 'weekly_load_hours', 'unavailable_periods',
        'scheduled_slots', 'planning_start_monday', '_max_defined_week'
    )

    def __init__(
        self,
        id,
        name,
        weekly_capacity_by_week=None,
        is_bottleneck=True,
    ):
        self.id = id
        self.name = name
        self.is_bottleneck = bool(is_bottleneck)

        self.work_start_time = time(0, 0)
        self.work_end_time = time(23, 59)
        self.lunch_start_time = time(0, 0)
        self.lunch_end_time = time(0, 0)

        self.daily_capacity_hours = 24.0

        self.weekly_capacity_by_week = weekly_capacity_by_week or {}

        self.weekly_load_hours = defaultdict(float)

        self.unavailable_periods = []
        self.scheduled_slots = []

        self.planning_start_monday = None

        self._max_defined_week = max(self.weekly_capacity_by_week.keys()) if self.weekly_capacity_by_week else 0

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
        return float(self.weekly_capacity_by_week.get(w, 0.0))

    def _weekly_hours_distribution(self, start_dt: datetime, end_dt: datetime):
        dist = defaultdict(float)
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
        if not self.is_bottleneck:
            return True
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, add_hours in dist.items():
            allowed = self._allowed_hours_for_week(start_dt)  # Note: using start_dt, but week determined by wk
            used = self.weekly_load_hours[wk]
            if used + add_hours > allowed + 1e-6:
                return False
        return True

    def _register_slot_in_week_load(self, start_dt: datetime, end_dt: datetime):
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, hours in dist.items():
            self.weekly_load_hours[wk] += hours

    def _recompute_weekly_load_from_slots(self):
        self.weekly_load_hours.clear()
        for s, e, _ in self.scheduled_slots:
            self._register_slot_in_week_load(s, e)

    def add_unavailable_period(self, start_date_str, end_date_str):
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
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
                current_dt = (current_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
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
            can_consume_seconds = min(remaining_seconds, 60)
            remaining_seconds -= can_consume_seconds
            current_dt = next_minute_dt

        if remaining_seconds > 0:
            return datetime.max
        return current_dt

    def _search_limit_datetime(self, search_start_dt_param: datetime):
        if not self.is_bottleneck:
            return search_start_dt_param + timedelta(days=365)

        if not self.weekly_capacity_by_week or self._max_defined_week <= 0:
            return search_start_dt_param + timedelta(days=365)

        self._ensure_planning_start(search_start_dt_param)
        last_monday = self.planning_start_monday + timedelta(days=7 * (self._max_defined_week - 1))
        last_end = datetime.combine(last_monday + timedelta(days=7), time.min)
        return max(search_start_dt_param + timedelta(days=1), last_end)

    def find_available_slot(self, search_start_dt_param: datetime, duration_hours: float,
                            of_id_to_ignore=None, reasons=None):
        """
        Cherche un créneau disponible.
        """
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = self._search_limit_datetime(search_start_dt_param)

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                if reasons is not None:
                    reasons.append(f"Le calcul de fin a échoué (boucle infinie) à partir de {current_try_start_dt}")
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt + timedelta(days=1))
                continue

            # Vérification capacité hebdomadaire
            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                wk = self._week_key(current_try_start_dt)
                allowed = self._allowed_hours_for_week(current_try_start_dt)
                used = self.weekly_load_hours[wk]
                # On calcule les heures supplémentaires approximatives
                dist = self._weekly_hours_distribution(current_try_start_dt, potential_end_dt)
                add_hours = dist.get(wk, 0)
                if reasons is not None:
                    reasons.append(f"Dépassement capacité semaine {wk}: déjà {used:.2f}h, ajout {add_hours:.2f}h, max {allowed:.2f}h")
                # Passer à la semaine suivante
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                current_try_start_dt = self._get_next_working_datetime(next_week_monday)
                continue

            # Vérification chevauchement
            is_overlap = False
            for booked_start, booked_end, booked_of_id in self.scheduled_slots:
                if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                    continue
                if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                    is_overlap = True
                    if reasons is not None:
                        reasons.append(f"Chevauchement avec OF {booked_of_id} (réservé {booked_start}–{booked_end})")
                    current_try_start_dt = self._get_next_working_datetime(booked_end)
                    break
            if is_overlap:
                continue

            # Aucun problème
            return current_try_start_dt, potential_end_dt

        return None, None

    def find_available_slot_bounded(self, search_start_dt_param: datetime, duration_hours: float,
                                    latest_end_dt: datetime, of_id_to_ignore=None, reasons=None):
        """
        Version avec borne de fin
        """
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = min(self._search_limit_datetime(search_start_dt_param), latest_end_dt)

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                if reasons is not None:
                    reasons.append(f"Calcul de fin infini à partir de {current_try_start_dt}")
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt + timedelta(days=1))
                continue

            if potential_end_dt > latest_end_dt:
                if reasons is not None:
                    reasons.append(f"La fin potentielle {potential_end_dt} dépasse la borne {latest_end_dt}")
                return None, None

            # Vérification capacité
            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                wk = self._week_key(current_try_start_dt)
                allowed = self._allowed_hours_for_week(current_try_start_dt)
                used = self.weekly_load_hours[wk]
                dist = self._weekly_hours_distribution(current_try_start_dt, potential_end_dt)
                add_hours = dist.get(wk, 0)
                if reasons is not None:
                    reasons.append(f"Dépassement capacité semaine {wk}: déjà {used:.2f}h, ajout {add_hours:.2f}h, max {allowed:.2f}h")
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                current_try_start_dt = self._get_next_working_datetime(next_week_monday)
                continue

            # Vérification chevauchement
            is_overlap = False
            for booked_start, booked_end, booked_of_id in self.scheduled_slots:
                if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                    continue
                if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                    is_overlap = True
                    if reasons is not None:
                        reasons.append(f"Chevauchement avec OF {booked_of_id} ({booked_start}–{booked_end})")
                    current_try_start_dt = self._get_next_working_datetime(booked_end)
                    break
            if is_overlap:
                continue

            return current_try_start_dt, potential_end_dt

        return None, None

    def find_available_slot_bounded(self, search_start_dt_param: datetime, duration_hours: float, latest_end_dt: datetime, of_id_to_ignore=None):
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = min(self._search_limit_datetime(search_start_dt_param), latest_end_dt)

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt + timedelta(days=1))
                continue

            if potential_end_dt > latest_end_dt:
                return None, None

            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
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
        self.scheduled_slots = [(s, e, o) for (s, e, o) in self.scheduled_slots if o != of_id]
        self._recompute_weekly_load_from_slots()

    def __repr__(self):
        return (
            f"Post(id={self.id}, name='{self.name}', "
            f"goulot={1 if self.is_bottleneck else 0}, "
            f"unavailable_periods={len(self.unavailable_periods)}, "
            f"scheduled_slots={len(self.scheduled_slots)})"
        )


class Operation:
    __slots__ = ('product_key', 'operation_name', 'post_id', 'standard_time_hours', 'sequence', 'priority')

    def __init__(self, product_key, operation_name, post_id, standard_time_hours, sequence, priority):
        self.product_key = _norm(product_key)
        self.operation_name = operation_name
        self.post_id = _norm(post_id)
        self.standard_time_hours = try_parse_float(standard_time_hours)
        self.sequence = int(sequence)
        self.priority = int(priority)


# ============================================================================
# GROUPING ALGORITHM 
# ============================================================================

def build_bom_graph(bom_data):
    """Build an undirected graph from BOM for connected components."""
    G = defaultdict(set)
    for b in bom_data:
        p = b.parent_product_id
        c = b.child_product_id
        if p and c:
            G[p].add(c)
            G[c].add(p)
    return G


def connected_component_nodes(G, start):
    start_norm = _norm(start)
    if not start_norm:
        return set()
    seen = set()
    q = deque([start_norm])
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
    # Compute product levels from BOM once
    product_level = {}
    for b in bom_data:
        p = b.parent_product_id
        c = b.child_product_id
        cl = b.child_bom_level
        pl = b.parent_bom_level
        if c and cl > 0:
            product_level[c] = max(product_level.get(c, 0), cl)
        if p and pl > 0:
            product_level[p] = max(product_level.get(p, 0), pl)

    for of in all_ofs:
        pid = of.product_id  
        lvl = product_level.get(pid, 0)
        of.effective_bom_level = lvl

    def get_level(of):
        return of.effective_bom_level

    bom_graph = build_bom_graph(bom_data)

    # Indexes for fast lookups
    ofs_by_id = {of.id: of for of in all_ofs}
    ofs_by_product = defaultdict(list)
    for of in all_ofs:
        ofs_by_product[of.product_id].append(of)

    # Set of unassigned OF ids
    unassigned_ids = {of.id for of in all_ofs if of.assigned_group_id is None}

    group_counter = 1
    groups = []
    skipped = set()

    while unassigned_ids:
        # Find anchor: highest level, earliest need date among unassigned not skipped
        best_of = None
        best_level = -1
        best_date = None
        for of_id in unassigned_ids:
            if of_id in skipped:
                continue
            of = ofs_by_id[of_id]
            lvl = get_level(of)
            if best_of is None or lvl > best_level or (lvl == best_level and of.need_date < best_date):
                best_of = of
                best_level = lvl
                best_date = of.need_date
        anchor_of = best_of
        if anchor_of is None:
            break

        anchor_pid_norm = anchor_of.product_id
        family = connected_component_nodes(bom_graph, anchor_of.product_id)
        if not family:
            family = {anchor_pid_norm}

        h_weeks = horizon_H_weeks_param
        if anchor_of.horizon_weeks not in (None, 0, ""):
            try:
                h_weeks = max(1, int(anchor_of.horizon_weeks))
            except Exception:
                h_weeks = horizon_H_weeks_param

        window_start = anchor_of.need_date
        window_end = window_start + timedelta(weeks=h_weeks) - timedelta(days=1)

        # Candidate OFs: unassigned, in window, product in family
        raw_candidates = []
        for pid in family:
            for of in ofs_by_product.get(pid, []):
                if of.id in unassigned_ids and window_start <= of.need_date <= window_end:
                    raw_candidates.append(of)

        cand_pids_raw = {of.product_id for of in raw_candidates}
        # Determine related PIDs 
        related_pids = set()
        for b in bom_data:
            p = b.parent_product_id
            c = b.child_product_id
            if p in cand_pids_raw and c in cand_pids_raw:
                related_pids.add(p)
                related_pids.add(c)

        candidates = [of for of in raw_candidates if of.product_id in related_pids]

        if len(candidates) <= 1 or anchor_of not in candidates:
            skipped.add(anchor_of.id)
            continue

        current_group = Group(
            id=f"GRP{group_counter}",
            ps_product_id=anchor_of.raw_product_id,
            initial_ps_of=anchor_of,
            window_start_date=window_start,
            window_end_date=window_end,
            initial_ps_as_stock=False,
        )

        # Sort candidates by level descending, then need date, then product id
        candidates_sorted = sorted(candidates, key=lambda o: (-get_level(o), o.need_date, o.product_id))
        for ofx in candidates_sorted:
            if ofx.id == anchor_of.id:
                continue
            current_group.add_of(ofx, ps_quantity_change=0)
            unassigned_ids.discard(ofx.id)

        # Remove anchor from unassigned set
        unassigned_ids.discard(anchor_of.id)

        current_group.calculate_consumption(bom_data)

        groups.append(current_group)
        group_counter += 1

    return groups, all_ofs


# ============================================================================
# SMOOTHING AND SCHEDULING 
# ============================================================================
def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    from collections import defaultdict as _dd
    import bisect

    def dt_to_str(dt):
        return dt.strftime("%Y-%m-%d %H:%M") if dt else None

    def days_delay_if_late(scheduled_end_dt, need_dt):
        if scheduled_end_dt is None:
            return 0
        delta = (scheduled_end_dt.date() - need_dt.date()).days
        return delta if delta > 0 else 0

    def qty_besoin_raw(of_obj):
        raw = getattr(of_obj, "source_qty", None)
        raw = (str(raw).strip() if raw is not None else "")
        if raw:
            return raw
        try:
            return str(float(getattr(of_obj, "quantity", 0) or 0))
        except Exception:
            return ""

    default_advance_weeks = int(params.get("advance_retreat_weeks", 3))
    default_retard_weeks = int(params.get("advance_retreat_weeks", 3))

    def get_advance_weeks(of_obj):
        v = getattr(of_obj, "advance_weeks", None)
        if v in (None, "", 0):
            return default_advance_weeks
        try:
            return max(0, int(v))
        except Exception:
            return default_advance_weeks

    def get_retard_weeks(of_obj):
        v = getattr(of_obj, "retard_weeks", None)
        if v in (None, "", 0):
            return default_retard_weeks
        try:
            return max(0, int(v))
        except Exception:
            return default_retard_weeks

    def week_bounds(dt_obj: datetime):
        monday = (dt_obj.date() - timedelta(days=dt_obj.weekday()))
        ws = datetime.combine(monday, time.min)
        we = ws + timedelta(days=7)
        return ws, we

    def candidate_week_starts(need_dt: datetime, advance_weeks: int, retard_weeks: int):
        adv_td = timedelta(weeks=advance_weeks)
        ret_td = timedelta(weeks=retard_weeks)
        earliest_start = need_dt - adv_td
        latest_end = need_dt + ret_td

        earliest_monday = (earliest_start.date() - timedelta(days=earliest_start.weekday()))
        need_monday = (need_dt.date() - timedelta(days=need_dt.weekday()))
        latest_monday = (latest_end.date() - timedelta(days=latest_end.weekday()))

        mondays = []
        cur = earliest_monday
        while cur <= latest_monday:
            mondays.append(datetime.combine(cur, time.min))
            cur += timedelta(days=7)

        need_monday_dt = datetime.combine(need_monday, time.min)
        earlier = [m for m in mondays if m < need_monday_dt]
        later = [m for m in mondays if m > need_monday_dt]

        earlier.sort(reverse=True)
        later.sort()

        result = []
        if need_monday_dt in mondays:
            result.append(need_monday_dt)
        result.extend(earlier)
        result.extend(later)
        return result

    # Initialisation du lundi de référence 
    all_need_dates = [of.need_date for of in all_ofs_with_groups if of.need_date]
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
        return getattr(of, "effective_bom_level", 0)

    # Index BOM 
    parent_to_children = _dd(set)
    bom_children = _dd(list)
    for b in bom_data:
        p = b.parent_product_id
        c = b.child_product_id
        if p and c:
            parent_to_children[p].add(c)
            bom_children[p].append((c, b.quantity_child_per_parent))

    def order_group_ofs_by_bom_chain(group_ofs):
        product_to_ofs = _dd(list)
        for of in group_ofs:
            product_to_ofs[of.product_id].append(of)

        for lst in product_to_ofs.values():
            lst.sort(key=lambda o: (o.need_date, o.id))

        product_level = {}
        for pn, ofs in product_to_ofs.items():
            levels = [get_level(of) for of in ofs]
            product_level[pn] = max(levels) if levels else 0

        products_sorted = sorted(product_to_ofs.keys(), key=lambda pn: -product_level.get(pn, 0))

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

    # STRUCTURES POUR LA GESTION GLOBALE DES STOCKS
    global_lots = _dd(list) 

    def check_component_availability(prod_norm, qty_parent, ignore_of_id=None):
        """
        Vérifie si la quantité nécessaire de composants est disponible dans les lots globaux.
        """
        children = bom_children.get(prod_norm, [])
        if not children:
            return True, None, {}, ""

        latest_ready = None
        allocations = {}

        for child_norm, coef in children:
            needed = qty_parent * coef
            if needed <= 0:
                continue

            lots = global_lots.get(child_norm, [])
            lots_sorted = sorted(lots, key=lambda l: l['end_dt'])
            remaining = needed
            child_ready = None
            tmp_alloc = []
            total_available = 0.0

            for idx, lot in enumerate(lots_sorted):
                if ignore_of_id and lot.get('of_id') == ignore_of_id:
                    continue
                free = lot['qty_free']
                if free <= 0:
                    continue
                take = min(free, remaining)
                if take <= 0:
                    continue
                remaining -= take
                total_available += take
                tmp_alloc.append((idx, take))
                child_ready = lot['end_dt']
                if remaining <= 1e-9:
                    break

            if remaining > 1e-9:
                child_raw = child_norm
                reason = f"Stock insuffisant pour composant {child_raw}: besoin={needed}, dispo={total_available}"
                return False, None, {}, reason

            allocations[child_norm] = tmp_alloc
            if child_ready and (latest_ready is None or child_ready > latest_ready):
                latest_ready = child_ready

        return True, latest_ready, allocations, ""

    def commit_allocations(allocations):
        for child_norm, uses in allocations.items():
            lots = global_lots.get(child_norm, [])
            if not lots:
                continue
            lots_sorted = sorted(lots, key=lambda l: l['end_dt'])
            for idx, qty_used in uses:
                if 0 <= idx < len(lots_sorted):
                    lots_sorted[idx]['qty_free'] -= qty_used
            global_lots[child_norm] = lots_sorted

    def add_produced_lot(prod_norm, end_dt, qty, of_id):
        global_lots[prod_norm].append({'end_dt': end_dt, 'qty_free': qty, 'of_id': of_id})
        global_lots[prod_norm] = sorted(global_lots[prod_norm], key=lambda l: l['end_dt'])

    # Fonction d'ordonnancement d'un OF individuel 
    def schedule_single_of(of_to_schedule, group_id=None):
        need_dt = of_to_schedule.need_date
        advance_w = get_advance_weeks(of_to_schedule)
        retard_w = get_retard_weeks(of_to_schedule)

        earliest_allowed = need_dt - timedelta(weeks=advance_w)
        latest_allowed = need_dt + timedelta(weeks=retard_w)

        prod_norm = of_to_schedule.product_id
        qty = of_to_schedule.quantity

        # Vérification stock composants (global)
        stock_ok, components_ready_dt, allocations, stock_reason = check_component_availability(
            prod_norm, qty, ignore_of_id=of_to_schedule.id
        )
        if not stock_ok:
            status = "ÉCHOUÉ(stock insuffisant)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None
            smoothing_items.append({
                "of_id": of_to_schedule.id,
                "product_id": of_to_schedule.raw_product_id,
                "designation": of_to_schedule.designation,
                "group_id": group_id if group_id else "INDIVIDUEL",
                "qty_besoin": qty_besoin_raw(of_to_schedule),
                "need_date": need_dt.strftime("%Y-%m-%d"),
                "scheduled_start": None,
                "scheduled_end": None,
                "status": status,
                "retard_jours": 0,
                "avance_jours": 0,
                "operations": [],
                "debug": stock_reason,
            })
            return of_to_schedule

        # Récupération des opérations
        key_of = of_to_schedule.normalized_id
        key_prod = prod_norm
        key_type = _norm(of_to_schedule.product_type)
        ops = (operations_map.get(key_of, []) or
               operations_map.get(key_prod, []) or
               operations_map.get(key_type, []))

        if not ops:
            status = "ÉCHOUÉ(poste indispo)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None
            smoothing_items.append({
                "of_id": of_to_schedule.id,
                "product_id": of_to_schedule.raw_product_id,
                "designation": of_to_schedule.designation,
                "group_id": group_id if group_id else "INDIVIDUEL",
                "qty_besoin": qty_besoin_raw(of_to_schedule),
                "need_date": need_dt.strftime("%Y-%m-%d"),
                "scheduled_start": None,
                "scheduled_end": None,
                "status": status,
                "retard_jours": 0,
                "avance_jours": 0,
                "operations": [],
                "debug": "No operations",
            })
            return of_to_schedule

        ops = sorted(ops, key=lambda o: o.sequence)

        for op_def in ops:
            post = posts_map.get(op_def.post_id)
            if post:
                post.clear_schedule_for_of(of_to_schedule.id + "_" + op_def.operation_name)

        chain_last_end = None
        op_sched = []
        feasible = True
        fail_reason = ""
        fail_post = None

        week_starts = candidate_week_starts(need_dt, advance_w, retard_w)

        for ws in week_starts:
            we = ws + timedelta(days=7)
            if ws > latest_allowed:
                break

            start_search = max(ws, earliest_allowed)
            if components_ready_dt is not None:
                start_search = max(start_search, components_ready_dt)

            chain_last_end = None
            op_sched_try = []
            ok = True
            fail_reason = ""
            fail_post = None

            for op_def in ops:
                post = posts_map.get(op_def.post_id)
                if not post:
                    fail_reason = f"Missing post {op_def.post_id}"
                    fail_post = op_def.post_id
                    ok = False
                    break

                dur_h = op_def.standard_time_hours

                if chain_last_end is not None:
                    start_search = max(start_search, chain_last_end)

                start_search = post._get_next_working_datetime(start_search)

                # Recherche avec collecte des raisons
                slot_reasons = []
                s_dt, e_dt = post.find_available_slot(
                    start_search,
                    dur_h,
                    of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name,
                    reasons=slot_reasons
                )

                if s_dt and e_dt and e_dt > latest_allowed:
                    s_dt, e_dt = None, None

                if not s_dt or not e_dt:
                    fail_reason = f"No slot on post {op_def.post_id}: " + "; ".join(slot_reasons)
                    fail_post = op_def.post_id
                    ok = False
                    break

                op_sched_try.append((op_def, post, s_dt, e_dt))
                chain_last_end = e_dt
                start_search = e_dt

            if ok and op_sched_try:
                op_sched = op_sched_try
                feasible = True
                break
            else:
                feasible = False

        if feasible and op_sched:
            for op_def, post, s_dt, e_dt in op_sched:
                post.book_slot(s_dt, e_dt, of_to_schedule.id + "_" + op_def.operation_name)

            start_dt = op_sched[0][2]
            end_dt = op_sched[-1][3]
            of_to_schedule.scheduled_start_date = start_dt
            of_to_schedule.scheduled_end_date = end_dt

            start_d = start_dt.date()
            if start_d <= need_dt.date():
                statut_calc = "OUI"
            elif need_dt.date() < start_d <= latest_allowed.date():
                statut_calc = "NON"
            else:
                statut_calc = "ÉCHOUÉ"

            statut = "NON" if statut_calc == "ÉCHOUÉ" else statut_calc
            of_to_schedule.status = statut

            retard_jours = days_delay_if_late(end_dt, need_dt) if statut == "NON" else 0
            if start_dt and start_dt < need_dt:
                avance_jours = (need_dt - start_dt).days
            else:
                avance_jours = 0

            commit_allocations(allocations)

            if qty > 0:
                add_produced_lot(prod_norm, end_dt, qty, of_to_schedule.id)

            smoothing_items.append({
                "of_id": of_to_schedule.id,
                "product_id": of_to_schedule.raw_product_id,
                "designation": of_to_schedule.designation,
                "group_id": group_id if group_id else "INDIVIDUEL",
                "qty_besoin": qty_besoin_raw(of_to_schedule),
                "need_date": need_dt.strftime("%Y-%m-%d"),
                "scheduled_start": dt_to_str(start_dt),
                "scheduled_end": dt_to_str(end_dt),
                "status": statut,
                "retard_jours": retard_jours,
                "avance_jours": avance_jours,
                "operations": [
                    {
                        "operation": d[0].operation_name,
                        "post_id": d[0].post_id,
                        "start": dt_to_str(d[2]),
                        "end": dt_to_str(d[3]),
                    }
                    for d in op_sched
                ],
            })
        else:
            status = "ÉCHOUÉ(poste indispo)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None

            smoothing_items.append({
                "of_id": of_to_schedule.id,
                "product_id": of_to_schedule.raw_product_id,
                "designation": of_to_schedule.designation,
                "group_id": group_id if group_id else "INDIVIDUEL",
                "qty_besoin": qty_besoin_raw(of_to_schedule),
                "need_date": need_dt.strftime("%Y-%m-%d"),
                "scheduled_start": None,
                "scheduled_end": None,
                "status": status,
                "retard_jours": 0,
                "avance_jours": 0,
                "operations": [],
                "debug": fail_reason or "No available slot within allowed advance/retard weeks",
            })

        return of_to_schedule

    # Construction de la file d'attente chronologique
    planning_queue = []  

    for group in groups:
        planning_queue.append(('group', group, group.time_window_start))

    for of in all_ofs_with_groups:
        if of.assigned_group_id is None:
            planning_queue.append(('individual', of, of.need_date))

    planning_queue.sort(key=lambda x: x[2])

    # Dictionnaire pour mémoriser les dernières fins sur chaque poste au sein d'un groupe
    group_post_last_end = {}

    # Parcours de la file
    for item_type, obj, ref_date in planning_queue:
        if item_type == 'group':
            group = obj
            group_ofs = [of for of in all_ofs_with_groups if of.assigned_group_id == group.id]
            ofs_sorted = order_group_ofs_by_bom_chain(group_ofs)

            group_post_last_end.clear()

            for of_to_schedule in ofs_sorted:
                need_dt = of_to_schedule.need_date
                advance_w = get_advance_weeks(of_to_schedule)
                retard_w = get_retard_weeks(of_to_schedule)
                earliest_allowed = need_dt - timedelta(weeks=advance_w)
                latest_allowed = need_dt + timedelta(weeks=retard_w)

                prod_norm = of_to_schedule.product_id
                qty = of_to_schedule.quantity

                # Vérification stock composants (global)
                stock_ok, components_ready_dt, allocations, stock_reason = check_component_availability(
                    prod_norm, qty, ignore_of_id=of_to_schedule.id
                )
                if not stock_ok:
                    status = "ÉCHOUÉ(stock insuffisant)"
                    of_to_schedule.status = status
                    of_to_schedule.scheduled_start_date = None
                    of_to_schedule.scheduled_end_date = None
                    smoothing_items.append({
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.raw_product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "qty_besoin": qty_besoin_raw(of_to_schedule),
                        "need_date": need_dt.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status,
                        "retard_jours": 0,
                        "avance_jours": 0,
                        "operations": [],
                        "debug": stock_reason,
                    })
                    scheduled_ofs.append(of_to_schedule)
                    continue

                # Récupération des opérations
                key_of = of_to_schedule.normalized_id
                key_prod = prod_norm
                key_type = _norm(of_to_schedule.product_type)
                ops = (operations_map.get(key_of, []) or
                       operations_map.get(key_prod, []) or
                       operations_map.get(key_type, []))

                if not ops:
                    status = "ÉCHOUÉ(poste indispo)"
                    of_to_schedule.status = status
                    of_to_schedule.scheduled_start_date = None
                    of_to_schedule.scheduled_end_date = None
                    smoothing_items.append({
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.raw_product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "qty_besoin": qty_besoin_raw(of_to_schedule),
                        "need_date": need_dt.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status,
                        "retard_jours": 0,
                        "avance_jours": 0,
                        "operations": [],
                        "debug": "No operations",
                    })
                    scheduled_ofs.append(of_to_schedule)
                    continue

                ops = sorted(ops, key=lambda o: o.sequence)

                for op_def in ops:
                    post = posts_map.get(op_def.post_id)
                    if post:
                        post.clear_schedule_for_of(of_to_schedule.id + "_" + op_def.operation_name)

                chosen_sched = None
                chosen_temp_post_end = None
                feasible = True
                fail_reason = ""
                fail_post = None

                week_starts = candidate_week_starts(need_dt, advance_w, retard_w)

                for ws in week_starts:
                    we = ws + timedelta(days=7)
                    if ws > latest_allowed:
                        break

                    start_search = max(ws, earliest_allowed)
                    if components_ready_dt is not None:
                        start_search = max(start_search, components_ready_dt)

                    chain_last_end = None
                    op_sched_try = []
                    temp_post_end = {}
                    ok = True
                    fail_reason = ""
                    fail_post = None

                    for op_def in ops:
                        post = posts_map.get(op_def.post_id)
                        if not post:
                            fail_reason = f"Missing post {op_def.post_id}"
                            fail_post = op_def.post_id
                            ok = False
                            break

                        dur_h = op_def.standard_time_hours
                        real_last = group_post_last_end.get(post.id)
                        tent_last = temp_post_end.get(post.id)
                        last_for_post = max([d for d in (real_last, tent_last) if d is not None], default=None)

                        if chain_last_end is not None:
                            start_search = max(start_search, chain_last_end)

                        if last_for_post is not None:
                            start_search = max(start_search, last_for_post)

                        start_search = post._get_next_working_datetime(start_search)

                        # Recherche avec collecte des raisons
                        slot_reasons = []
                        s_dt, e_dt = post.find_available_slot(
                            start_search,
                            dur_h,
                            of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name,
                            reasons=slot_reasons
                        )

                        if s_dt and e_dt and e_dt > latest_allowed:
                            s_dt, e_dt = None, None

                        if not s_dt or not e_dt:
                            fail_reason = f"No slot on post {op_def.post_id}: " + "; ".join(slot_reasons)
                            fail_post = op_def.post_id
                            ok = False
                            break

                        op_sched_try.append((op_def, post, s_dt, e_dt))
                        chain_last_end = e_dt
                        temp_post_end[post.id] = e_dt
                        start_search = e_dt

                    if ok and op_sched_try:
                        chosen_sched = op_sched_try
                        chosen_temp_post_end = temp_post_end
                        break

                if chosen_sched:
                    for op_def, post, s_dt, e_dt in chosen_sched:
                        post.book_slot(s_dt, e_dt, of_to_schedule.id + "_" + op_def.operation_name)

                    for pid, enddt in (chosen_temp_post_end or {}).items():
                        if group_post_last_end.get(pid) is None or enddt > group_post_last_end[pid]:
                            group_post_last_end[pid] = enddt

                    start_dt = chosen_sched[0][2]
                    end_dt = chosen_sched[-1][3]
                    of_to_schedule.scheduled_start_date = start_dt
                    of_to_schedule.scheduled_end_date = end_dt

                    start_d = start_dt.date()
                    if start_d <= need_dt.date():
                        statut_calc = "OUI"
                    elif need_dt.date() < start_d <= latest_allowed.date():
                        statut_calc = "NON"
                    else:
                        statut_calc = "ÉCHOUÉ"

                    statut = "NON" if statut_calc == "ÉCHOUÉ" else statut_calc
                    of_to_schedule.status = statut

                    retard_jours = days_delay_if_late(end_dt, need_dt) if statut == "NON" else 0
                    if start_dt and start_dt < need_dt:
                        avance_jours = (need_dt - start_dt).days
                    else:
                        avance_jours = 0

                    commit_allocations(allocations)

                    if qty > 0:
                        add_produced_lot(prod_norm, end_dt, qty, of_to_schedule.id)

                    smoothing_items.append({
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.raw_product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "qty_besoin": qty_besoin_raw(of_to_schedule),
                        "need_date": need_dt.strftime("%Y-%m-%d"),
                        "scheduled_start": dt_to_str(start_dt),
                        "scheduled_end": dt_to_str(end_dt),
                        "status": statut,
                        "retard_jours": retard_jours,
                        "avance_jours": avance_jours,
                        "operations": [
                            {
                                "operation": d[0].operation_name,
                                "post_id": d[0].post_id,
                                "start": dt_to_str(d[2]),
                                "end": dt_to_str(d[3]),
                            }
                            for d in chosen_sched
                        ],
                    })
                else:
                    status = "ÉCHOUÉ(poste indispo)"
                    of_to_schedule.status = status
                    of_to_schedule.scheduled_start_date = None
                    of_to_schedule.scheduled_end_date = None
                    smoothing_items.append({
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.raw_product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "qty_besoin": qty_besoin_raw(of_to_schedule),
                        "need_date": need_dt.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": status,
                        "retard_jours": 0,
                        "avance_jours": 0,
                        "operations": [],
                        "debug": fail_reason or "No slot within allowed advance/retard weeks",
                    })

                scheduled_ofs.append(of_to_schedule)

        else:  # item_type == 'individual'
            of_to_schedule = obj
            schedule_single_of(of_to_schedule, group_id=None)
            scheduled_ofs.append(of_to_schedule)

    # Reconstruction de la liste finale
    final_by_id = {of.id: of for of in scheduled_ofs}
    updated_all = [final_by_id.get(orig.id, orig) for orig in all_ofs_with_groups]

    # Calcul et affichage du nombre d'OFs échoués
    failed_count = sum(1 for item in smoothing_items if "ÉCHOUÉ" in item.get("status", ""))
    print(f"[Smoothing] Nombre total d'OFs échoués : {failed_count}")

    # Écriture des fichiers 
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": smoothing_items}
    try:
        with open(smoothing_json_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Smoothing] JSON write error: {e}")

    smoothing_csv_path = params.get("smoothing_csv_path")
    if not smoothing_csv_path:
        smoothing_csv_path = os.path.join(os.path.dirname(smoothing_json_path), "smoothing_report.csv")

    if smoothing_csv_path:
        try:
            write_smoothing_csv(smoothing_items, smoothing_csv_path)
            print(f"[Smoothing] CSV report written to {smoothing_csv_path}")
        except Exception as e:
            print(f"[Smoothing] CSV report error: {e}")

    weekly_capacity_report_path = params.get("weekly_capacity_report_path")
    if weekly_capacity_report_path:
        try:
            write_posts_weekly_capacity_report(posts_map, weekly_capacity_report_path)
            print(f"[Smoothing] Weekly capacity report written to {weekly_capacity_report_path}")
        except Exception as e:
            print(f"[Smoothing] Weekly capacity report error: {e}")

    return updated_all


# ============================================================================
# OUTPUT WRITERS
# ============================================================================

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
        return getattr(of_obj, "effective_bom_level", 0)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(output_header)

        ofs_by_id = {of.id: of for of in all_ofs_scheduled}
        grouped_ids = set()

        def extract_group_number(group):
            try:
                return int(group.id.replace("GRP", ""))
            except Exception:
                return 0

        for group in sorted(grouped_list_data, key=extract_group_number):
            f.write(f"\n# Group ID: {group.id}\n")
            f.write(f"#   Produit PS Principal (ancre): {group.raw_ps_product_id}\n")
            f.write(
                f"#   Fenêtre Temporelle: "
                f"{group.time_window_start.strftime('%Y-%m-%d')} à "
                f"{group.time_window_end.strftime('%Y-%m-%d')}\n"
            )

            product_norm_to_raw = {}
            ofs_in_group = []
            for of in group.ofs:
                ofs_in_group.append(of)
                grouped_ids.add(of.id)
                pn = of.product_id
                if pn not in product_norm_to_raw:
                    product_norm_to_raw[pn] = of.raw_product_id

            if hasattr(group, "individual_product_stocks") and group.ps_product_id in group.individual_product_stocks:
                f.write(f"#   Stock PS Calculé: {group.individual_product_stocks[group.ps_product_id]}\n")
            else:
                f.write("#   Stock PS: Non calculé / Ancre composant\n")

            product_totals = defaultdict(lambda: {"demande": 0.0, "produit": 0.0})
            for of in ofs_in_group:
                pn = of.product_id
                q_dem = of.quantity
                q_prod = of.individual_product_stock
                product_totals[pn]["demande"] += q_dem
                product_totals[pn]["produit"] += q_prod

            pf_norms = sorted({of.product_id for of in ofs_in_group if of.product_type == "PF"})

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

            ofs_in_group_sorted = sorted(ofs_in_group, key=lambda x: (get_bom_level(x), x.need_date, x.product_id))

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
                grp_flg = group.id.replace("GRP", "")
                start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""

                delay_val = "0"
                if of_obj.status == "NON" and of_obj.scheduled_end_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_end_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))

                stock_val = of_obj.individual_product_stock if of_obj.individual_product_stock is not None else of_obj.quantity

                writer.writerow(
                    [
                        of_obj.raw_product_id,
                        processed_description,
                        processed_order_code,
                        of_obj.fg,
                        of_obj.cat,
                        of_obj.us,
                        of_obj.fs,
                        of_obj.quantity,
                        of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                        grp_flg,
                        start_date_str,
                        delay_val,
                        stock_val,
                    ]
                )

        unassigned = [of for of in all_ofs_scheduled if of.id not in grouped_ids]
        if unassigned:
            f.write("\n# OFs Non Affectés:\n")
            unassigned_sorted = sorted(unassigned, key=lambda x: (get_bom_level(x), x.need_date, x.id))
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

                processed_order_code = of_obj.id[:10] if len(of_obj.id) > 10 else of_obj.id
                grp_flg = ""
                start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""

                delay_val = "0"
                if of_obj.status == "NON" and of_obj.scheduled_end_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_end_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))

                stock_val = of_obj.individual_product_stock if of_obj.individual_product_stock is not None else of_obj.quantity

                writer.writerow(
                    [
                        of_obj.raw_product_id,
                        processed_description,
                        processed_order_code,
                        of_obj.fg,
                        of_obj.cat,
                        of_obj.us,
                        of_obj.fs,
                        int(of_obj.quantity) if isinstance(of_obj.quantity, (int, float)) else of_obj.quantity,
                        of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                        grp_flg,
                        start_date_str,
                        delay_val,
                        stock_val,
                    ]
                )

    print(f"Output written to {filepath}. Total OFs: {len(all_ofs_scheduled)}, Groupés: {len(grouped_ids)}, Non affectés: {len(unassigned)}")


def write_smoothing_csv(smoothing_items, output_filepath):
    import csv
    import os
    os.makedirs(os.path.dirname(output_filepath), exist_ok=True)

    header = ["Groupe", "OF", "Date de besoin", "Statut"]
    with open(output_filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)
        for item in smoothing_items:
            group_id = item.get("group_id", "INDIVIDUEL")
            of_id = item.get("of_id", "")
            need_date = item.get("need_date", "")
            status = item.get("status", "")
            if need_date and " " in need_date:
                need_date = need_date.split(" ")[0]
            writer.writerow([group_id, of_id, need_date, status])
    print(f"✅ Fichier CSV du lissage généré (ordre original conservé) : {output_filepath}")


def write_posts_weekly_capacity_report(posts_map, output_filepath):
    import csv
    import os
    from datetime import datetime, timedelta, time

    folder = os.path.dirname(output_filepath)
    if folder:
        os.makedirs(folder, exist_ok=True)

    header = [
        "PostID",
        "PostName",
        "Goulot",
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

            is_bottleneck = bool(getattr(post, "is_bottleneck", True))
            goulot_val = 1 if is_bottleneck else 0

            for wk_index, planned in sorted(post.weekly_load_hours.items()):
                week_start = base + timedelta(days=7 * (wk_index - 1))
                week_end = week_start + timedelta(days=6)

                if not is_bottleneck:
                    writer.writerow(
                        [
                            post.id,
                            post.name,
                            goulot_val,
                            wk_index,
                            week_start.strftime("%Y-%m-%d"),
                            week_end.strftime("%Y-%m-%d"),
                            "INF",
                            round(float(planned), 2),
                            "",
                            "N/A",
                        ]
                    )
                    continue

                dt_for_wk = datetime.combine(week_start, time.min)
                allowed = float(post._allowed_hours_for_week(dt_for_wk))
                delta = allowed - float(planned)
                respect = "OUI" if planned <= allowed + 1e-6 else "NON"

                writer.writerow(
                    [
                        post.id,
                        post.name,
                        goulot_val,
                        wk_index,
                        week_start.strftime("%Y-%m-%d"),
                        week_end.strftime("%Y-%m-%d"),
                        round(allowed, 2),
                        round(float(planned), 2),
                        round(delta, 2),
                        respect,
                    ]
                )


# ============================================================================
# LOADERS 
# ============================================================================

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
        "horizon": ["horizon", "horizon (weeks)", "horizon_weeks", "fenetre", "window"],
        "retard": ["retard", "delay", "advance_retreat", "advance_retreat_weeks", "retard_weeks"],
        "avance": ["avance", "advance", "advance weeks", "avance (weeks)"],
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

        h_hit = None
        for k in ["Horizon"] + ALIASES.get("horizon", []):
            if k.lower() in lower:
                h_hit = lower[k.lower()]
                break
        out["_HORIZON_OPT_"] = h_hit

        r_hit = None
        for k in ["Retard"] + ALIASES.get("retard", []):
            if k.lower() in lower:
                r_hit = lower[k.lower()]
                break
        out["_RETARD_OPT_"] = r_hit

        #recherche colonne Avance
        a_hit = None
        for k in ["Avance"] + ALIASES.get("avance", []):
            if k.lower() in lower:
                a_hit = lower[k.lower()]
                break
        out["_AVANCE_OPT_"] = a_hit

        return out

    f, reader, used_delim, used_enc = _make_reader(filepath, required_cols=None, fallback="\t")
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
            f"CSV file {filepath} missing required columns. Found: {reader.fieldnames}"
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

                horizon_val = None
                h_col = mapped_cols.get("_HORIZON_OPT_")
                if h_col:
                    horizon_val = row.get(h_col)

                retard_val = None
                r_col = mapped_cols.get("_RETARD_OPT_")
                if r_col:
                    retard_val = row.get(r_col)

                #lecture de la colonne Avance
                advance_val = None
                a_col = mapped_cols.get("_AVANCE_OPT_")
                if a_col:
                    advance_val = row.get(a_col)

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
                    horizon_weeks=horizon_val,
                    retard_weeks=retard_val,
                    advance_weeks=advance_val,
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

    required_cols = ["ParentProductID", "ChildProductID", "QuantityChildPerParent", "ChildBOMLevel"]

    aliases = {
        "ParentProductID": ["parentproductid", "parent", "parent id", "id parent"],
        "ChildProductID": ["childproductid", "child", "child id", "id child"],
        "QuantityChildPerParent": ["quantitychildperparent", "qty/parent", "qty_per_parent", "qte/parent"],
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

    f, reader, used_delim, used_enc = _make_reader(filepath, required_cols=None, fallback=",")
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
        required_cols_posts = ["PostID", "PostName"]

        f_posts, reader_posts, used_delim_posts, used_enc_posts = _make_reader(
            filepath_posts, required_cols=None, fallback=","
        )
        if not reader_posts or not reader_posts.fieldnames:
            raise FileNotFoundError(f"Posts CSV {filepath_posts} appears empty or has no header.")

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

        goulot_col = None
        for c in reader_posts.fieldnames:
            if c.strip().lower().replace(" ", "") in ("goulot", "bottleneck"):
                goulot_col = c.strip()
                break

        def parse_goulot(v):
            s = str(v or "").strip().lower()
            if s in ("1", "oui", "true", "yes", "y"):
                return True
            if s in ("0", "non", "false", "no", "n"):
                return False
            return True

        week_cols = {}
        for col in reader_posts.fieldnames:
            key_norm = col.strip().lower().replace(" ", "")
            m = re.match(r"week(\d+)", key_norm)
            if m:
                week_index = int(m.group(1))
                week_cols[week_index] = col.strip()

        if not week_cols:
            print("[WARN] Aucun champ WeekX trouvé dans posts CSV. Les goulots auront 0h partout => échec planification.")

        for row in reader_posts:
            raw_pid = row[colmap_posts["PostID"]]
            pid = norm_code(raw_pid)

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

            is_bottleneck = True
            if goulot_col is not None:
                is_bottleneck = parse_goulot(row.get(goulot_col, "1"))

            post = Post(
                id=pid,
                name=row[colmap_posts["PostName"]],
                weekly_capacity_by_week=weekly_capacity_by_week,
                is_bottleneck=is_bottleneck,
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
                filepath_post_unavailability, required_cols=None, fallback=","
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
        f_ops, reader_ops, used_delim_ops, used_enc_ops = _make_reader(filepath_operations, required_cols=None, fallback=",")
        if not reader_ops or not reader_ops.fieldnames:
            raise FileNotFoundError(f"Operations file {filepath_operations} appears empty or has no header.")

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
                raise ValueError(f"Column '{wanted}' not found in operations file. Found: {reader_ops.fieldnames}")
            colmap_ops[wanted] = hit

        for row in reader_ops:
            raw_key = row.get(colmap_ops["ProductID"]) or row.get("ProductType") or "UNKNOWN_OP_KEY"
            key = norm_code(raw_key)
            if key == "UNKNOWN_OP_KEY" or not key:
                continue

            post_id_norm = norm_code(row.get(colmap_ops["PostID"], ""))

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

    print(f"Loaded {len(posts_map)} posts and {sum(len(ops) for ops in operations_map.values())} operation rules.")
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
                                advance_weeks=None,   
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


# ============================================================================
# MAIN
# ============================================================================

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

    posts_map, operations_map = load_posts_and_operations_data(posts_file, post_unavailability_file, operations_file)

    print(f"[DEBUG] Nb posts: {len(posts_map)}")
    print(f"[DEBUG] Nb clés opérations: {len(operations_map)}")
    print(f"[DEBUG] Exemple clés opérations: {list(operations_map.keys())[:10]}")

    params = {
        "advance_retreat_weeks": ADVANCE_RETREAT_WEEKS,
        "weekly_capacity_report_path": "uploads/weekly_capacity_report.csv",
        "smoothing_csv_path": "uploads/smoothing_report.csv",
    }

    groups, all_ofs_with_groups = run_grouping_algorithm(all_ofs, bom_data, HORIZON_H_WEEKS)

    all_ofs_scheduled = smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params)

    write_grouped_needs_to_file(output_file, groups, all_ofs_scheduled)
    print(f"\nDone -> {output_file}")