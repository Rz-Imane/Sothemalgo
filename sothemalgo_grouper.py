from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import calendar
import csv
import os
import re
import json
from functools import lru_cache


# CONSTANTS
HORIZON_H_MONTHS = 2
HORIZON_H_WEEKS = 10
ADVANCE_RETREAT_WEEKS = 3          
ENCODING_CANDIDATES = [
    "utf-8",
    "utf-8-sig",
    "cp1252",
    "ISO-8859-1",
]


# UTILITY FUNCTIONS
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
            print(f"Trying encoding: {enc}")
            f = open(filepath, "r", encoding=enc, errors='replace', newline="")
            reader = csv.DictReader(f, delimiter=delim)
            cols = reader.fieldnames
            if not cols:
                f.close()
                continue
            print(f"SUCCESS with {enc}")
            return f, reader, delim, enc
        except FileNotFoundError:
            return None, None, fallback, None
        except Exception as e:
            print(f"FAILED with {enc}: {e}")
            last_err = e
            try:
                f.close()
            except:
                pass
            continue
    # Fallback ultime
    try:
        print("Trying fallback latin-1")
        f = open(filepath, "r", encoding="latin-1", errors='replace', newline="")
        reader = csv.DictReader(f, delimiter=delim)
        if reader.fieldnames:
            print("SUCCESS with latin-1 fallback")
            return f, reader, delim, "latin-1"
        f.close()
    except Exception as e:
        print(f"Fallback failed: {e}")
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


# CACHED BOM FUNCTIONS
@lru_cache(maxsize=None)
def find_qty_of_component_in_product_cached(product_to_make_id, component_to_find_id, bom_tuple):
    if product_to_make_id == component_to_find_id:
        return 1.0
    total = 0.0
    for parent, child, qty in bom_tuple:
        if parent == product_to_make_id:
            total += qty * find_qty_of_component_in_product_cached(child, component_to_find_id, bom_tuple)
    return total


def prepare_bom_tuple(bom_data):
    return tuple((b.parent_product_id, b.child_product_id, b.quantity_child_per_parent) for b in bom_data)


# CLASSES
class ManufacturingOrder:
    __slots__ = (
        'id', 'designation', 'product_id', 'raw_product_id', 'product_type',
        'bom_level', 'need_date', 'source_qty', 'quantity', 'unit',
        'horizon_weeks', 'retard_weeks', 'advance_weeks',
        'assigned_group_id', 'status',
        'scheduled_start_date', 'scheduled_end_date', 'fg', 'cat', 'us', 'fs',
        'individual_product_stock', 'effective_bom_level', 'normalized_id', 'normalized_product',
        'priority'                        
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
        priority=None                    
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

        self.normalized_id = _norm(self.id)
        self.normalized_product = self.product_id   

        self.priority = priority          

    def __repr__(self):
        lvl = getattr(self, "effective_bom_level", self.bom_level)
        return (
            f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.raw_product_id}', "
            f"type='{self.product_type}', level={lvl}, "
            f"need={self.need_date.strftime('%Y-%m-%d')}, qty={self.quantity}, "
            f"fg='{self.fg}', cat='{self.cat}', indiv_stock={self.individual_product_stock}, "
            f"group={self.assigned_group_id}, status='{self.status}', priority={self.priority})"
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

        produced_qty = defaultdict(float)
        for of in self.ofs:
            produced_qty[of.product_id] += of.quantity

        if not produced_qty:
            self._clear_and_reset()
            return

        for pid in produced_qty:
            if pid not in product_level:
                product_level[pid] = 0

        levels = set(product_level[pid] for pid in produced_qty)
        max_level = max(levels) if levels else 0
        min_level = min(levels) if levels else 0

        bom_by_parent = defaultdict(list)
        for bom in bom_data:
            p = bom.parent_product_id
            if p in produced_qty:
                bom_by_parent[p].append((bom.child_product_id, bom.quantity_child_per_parent))

        product_stock = defaultdict(float)
        product_consumption = defaultdict(float)

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
        'weekly_capacity_by_week', 'weekly_load_hours', 'weekly_remaining_capacity',
        'unavailable_periods', 'scheduled_slots', 'slots_by_week',
        'planning_start_monday', '_max_defined_week', '_first_week_index', '_last_week_index',
        '_first_week_date', '_last_week_date'
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

        # Garder uniquement les semaines avec capacité > 0
        if weekly_capacity_by_week:
            self.weekly_capacity_by_week = {wk: cap for wk, cap in weekly_capacity_by_week.items() if cap > 0}
        else:
            self.weekly_capacity_by_week = {}

        self.weekly_load_hours = defaultdict(float)
        self.weekly_remaining_capacity = defaultdict(float)

        for wk, cap in self.weekly_capacity_by_week.items():
            self.weekly_remaining_capacity[wk] = float(cap)

        self.unavailable_periods = []
        self.scheduled_slots = []
        self.slots_by_week = defaultdict(list)

        self.planning_start_monday = None
        self._max_defined_week = max(self.weekly_capacity_by_week.keys()) if self.weekly_capacity_by_week else 0
        self._first_week_index = None
        self._last_week_index = None
        self._first_week_date = None
        self._last_week_date = None

    def set_week0_monday(self, monday_date):
        """Appeler une seule fois après chargement des capacités."""
        self.planning_start_monday = monday_date
        if self.weekly_capacity_by_week:
            self._first_week_index = min(self.weekly_capacity_by_week.keys())
            self._last_week_index = max(self.weekly_capacity_by_week.keys())
            # Convertir en datetime au début de la journée
            self._first_week_date = datetime.combine(
                self.planning_start_monday + timedelta(days=7 * (self._first_week_index - 1)),
                time.min
            )
            self._last_week_date = datetime.combine(
                self.planning_start_monday + timedelta(days=7 * self._last_week_index),
                time.min
            )

    def _ensure_planning_start(self, dt_obj: datetime):
        if self.planning_start_monday is None:
            d = dt_obj.date()
            self.planning_start_monday = d - timedelta(days=d.weekday())
            if self.weekly_capacity_by_week:
                self._first_week_index = min(self.weekly_capacity_by_week.keys())
                self._last_week_index = max(self.weekly_capacity_by_week.keys())
                self._first_week_date = datetime.combine(
                    self.planning_start_monday + timedelta(days=7 * (self._first_week_index - 1)),
                    time.min
                )
                self._last_week_date = datetime.combine(
                    self.planning_start_monday + timedelta(days=7 * self._last_week_index),
                    time.min
                )

    def _relative_week_index(self, dt_obj: datetime) -> int:
        if self.planning_start_monday is None:
            self._ensure_planning_start(dt_obj)
        delta_days = (dt_obj.date() - self.planning_start_monday).days
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

    def _has_any_capacity_in_week(self, dt_obj: datetime) -> bool:
        if not self.is_bottleneck:
            return True
        wk = self._relative_week_index(dt_obj)
        if self._first_week_index is not None and wk < self._first_week_index:
            return False
        if self._last_week_index is not None and wk > self._last_week_index:
            return False
        remaining = self.weekly_remaining_capacity.get(wk, 0.0)
        return remaining > 1e-6

    def _can_add_slot_in_week(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.is_bottleneck:
            return True
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, add_hours in dist.items():
            if self._first_week_index is not None and wk < self._first_week_index:
                return False
            if self._last_week_index is not None and wk > self._last_week_index:
                return False
            remaining = self.weekly_remaining_capacity.get(wk, 0.0)
            if add_hours > remaining + 1e-6:
                return False
        return True

    def _register_slot_in_week_load(self, start_dt: datetime, end_dt: datetime):
        dist = self._weekly_hours_distribution(start_dt, end_dt)
        for wk, hours in dist.items():
            self.weekly_load_hours[wk] += hours
            if self.is_bottleneck:
                self.weekly_remaining_capacity[wk] = max(
                    0.0,
                    self.weekly_remaining_capacity.get(wk, 0.0) - hours
                )

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
        current_dt = current_dt_orig.replace(second=0, microsecond=0)
        max_iterations = 500
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            wd = current_dt.weekday()
            if wd >= 5:
                days_to_monday = 7 - wd
                current_dt = datetime.combine(
                    (current_dt + timedelta(days=days_to_monday)).date(), time.min
                )
                continue
            moved = False
            for un_start, un_end in self.unavailable_periods:
                if un_start <= current_dt <= un_end:
                    current_dt = (un_end + timedelta(minutes=1)).replace(second=0, microsecond=0)
                    moved = True
                    break
            if moved:
                continue
            return current_dt
        return current_dt_orig

    def calculate_end_datetime(self, start_dt_param: datetime, duration_hours: float):
        if duration_hours <= 0:
            return start_dt_param
        actual_start = self._get_next_working_datetime(start_dt_param)
        self._ensure_planning_start(actual_start)
        remaining_hours = duration_hours
        current_dt = actual_start
        max_weeks = 520
        for _ in range(max_weeks):
            if remaining_hours <= 0:
                break
            wk = self._relative_week_index(current_dt)
            if self._last_week_index is not None and wk > self._last_week_index:
                return datetime.max
            monday_of_wk = self.planning_start_monday + timedelta(days=7 * (wk - 1))
            week_end_dt = datetime.combine(monday_of_wk + timedelta(days=7), time.min)
            hours_to_week_end = self._working_hours_between(current_dt, week_end_dt)
            if hours_to_week_end <= 0:
                next_monday = week_end_dt
                next_working = self._get_next_working_datetime(next_monday)
                if next_working <= current_dt:
                    next_working = self._get_next_working_datetime(week_end_dt + timedelta(days=1))
                current_dt = next_working
                continue
            if remaining_hours <= hours_to_week_end:
                return self._advance_working_hours(current_dt, remaining_hours)
            else:
                remaining_hours -= hours_to_week_end
                current_dt = self._get_next_working_datetime(week_end_dt)
        return datetime.max

    def _working_hours_between(self, start_dt: datetime, end_dt: datetime) -> float:
        if end_dt <= start_dt:
            return 0.0
        total = 0.0
        current = start_dt
        while current < end_dt:
            wd = current.weekday()
            if wd >= 5:
                days_to_monday = 7 - wd
                current = datetime.combine((current + timedelta(days=days_to_monday)).date(), time.min)
                continue
            next_day = datetime.combine((current + timedelta(days=1)).date(), time.min)
            segment_end = min(end_dt, next_day)
            seg_hours = (segment_end - current).total_seconds() / 3600.0
            for un_start, un_end in self.unavailable_periods:
                overlap_start = max(current, un_start)
                overlap_end = min(segment_end, un_end)
                if overlap_end > overlap_start:
                    seg_hours -= (overlap_end - overlap_start).total_seconds() / 3600.0
            total += max(0.0, seg_hours)
            current = segment_end
        return total

    def _advance_working_hours(self, start_dt: datetime, hours: float) -> datetime:
        if hours <= 0:
            return start_dt
        remaining = hours
        current = start_dt
        max_iterations = 3650
        iteration = 0
        while remaining > 1e-9:
            iteration += 1
            if iteration > max_iterations:
                return current
            wd = current.weekday()
            if wd >= 5:
                days_to_monday = 7 - wd
                current = datetime.combine(
                    (current + timedelta(days=days_to_monday)).date(), time.min
                )
                continue
            in_unavail = False
            for un_start, un_end in self.unavailable_periods:
                if un_start <= current <= un_end:
                    current = un_end + timedelta(minutes=1)
                    in_unavail = True
                    break
            if in_unavail:
                continue
            next_day = datetime.combine((current + timedelta(days=1)).date(), time.min)
            segment_end = next_day
            for un_start, un_end in self.unavailable_periods:
                if un_start > current:
                    segment_end = min(segment_end, un_start)
            avail_hours = (segment_end - current).total_seconds() / 3600.0
            if avail_hours <= 0:
                current = segment_end + timedelta(minutes=1)
                continue
            if remaining <= avail_hours:
                result = current + timedelta(hours=remaining)
                return self._get_next_working_datetime(result)
            remaining -= avail_hours
            current = segment_end

    def _search_limit_datetime(self, search_start_dt_param: datetime):
        if not self.is_bottleneck:
            return search_start_dt_param + timedelta(days=365)
        if self._last_week_date is not None:
            return self._last_week_date
        return search_start_dt_param + timedelta(days=365)

    def find_available_slot(self, search_start_dt_param: datetime, duration_hours: float,
                            of_id_to_ignore=None, reasons=None):
        if self.is_bottleneck and self._first_week_date is not None:
            if search_start_dt_param < self._first_week_date:
                if reasons is not None:
                    reasons.append(f"Recherche avant {self._first_week_date} → décalée à cette date")
                search_start_dt_param = self._first_week_date

        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = self._search_limit_datetime(search_start_dt_param)

        while current_try_start_dt < max_search_datetime:
            if self.is_bottleneck and self._last_week_date is not None:
                if current_try_start_dt >= self._last_week_date:
                    if reasons is not None:
                        reasons.append(f"Dépassement de la dernière semaine de capacité ({self._last_week_date})")
                    break

            if not self._has_any_capacity_in_week(current_try_start_dt):
                if reasons is not None:
                    wk = self._relative_week_index(current_try_start_dt)
                    reasons.append(f"Semaine {wk} hors plage ou saturée")
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                candidate = self._get_next_working_datetime(next_week_monday)
                if candidate <= current_try_start_dt:
                    candidate = self._get_next_working_datetime(next_week_monday + timedelta(days=1))
                current_try_start_dt = candidate
                continue

            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                if reasons is not None:
                    reasons.append(f"Impossible de calculer la fin à partir de {current_try_start_dt}")
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt + timedelta(days=1))
                continue

            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                wk = self._relative_week_index(current_try_start_dt)
                allowed = self._allowed_hours_for_week(current_try_start_dt)
                used = self.weekly_load_hours[wk]
                dist = self._weekly_hours_distribution(current_try_start_dt, potential_end_dt)
                add_hours = dist.get(wk, 0)
                if reasons is not None:
                    reasons.append(f"Capacité insuffisante semaine {wk}: dispo {allowed-used:.2f}h, besoin {add_hours:.2f}h")
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                candidate = self._get_next_working_datetime(next_week_monday)
                if candidate <= current_try_start_dt:
                    candidate = self._get_next_working_datetime(next_week_monday + timedelta(days=1))
                current_try_start_dt = candidate
                continue

            is_overlap = False
            wk_start = self._relative_week_index(current_try_start_dt)
            wk_end = self._relative_week_index(potential_end_dt)
            for wk_check in range(wk_start, wk_end + 1):
                for booked_start, booked_end, booked_of_id in self.slots_by_week.get(wk_check, []):
                    if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                        continue
                    if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                        is_overlap = True
                        if reasons is not None:
                            reasons.append(f"Chevauchement avec OF {booked_of_id} ({booked_start}–{booked_end})")
                        current_try_start_dt = self._get_next_working_datetime(booked_end)
                        break
                if is_overlap:
                    break
            if is_overlap:
                continue

            return current_try_start_dt, potential_end_dt

        return None, None

    def find_available_slot_bounded(self, search_start_dt_param: datetime, duration_hours: float,
                                    latest_end_dt: datetime, of_id_to_ignore=None, reasons=None):
        if self.is_bottleneck and self._first_week_date is not None:
            if search_start_dt_param < self._first_week_date:
                if reasons is not None:
                    reasons.append(f"Recherche avant {self._first_week_date} → décalée")
                search_start_dt_param = self._first_week_date

        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = min(self._search_limit_datetime(search_start_dt_param), latest_end_dt)

        while current_try_start_dt < max_search_datetime:
            if self.is_bottleneck and self._last_week_date is not None:
                if current_try_start_dt >= self._last_week_date:
                    break

            if not self._has_any_capacity_in_week(current_try_start_dt):
                if reasons is not None:
                    wk = self._relative_week_index(current_try_start_dt)
                    reasons.append(f"Semaine {wk} hors plage ou saturée")
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                candidate = self._get_next_working_datetime(next_week_monday)
                if candidate <= current_try_start_dt:
                    candidate = self._get_next_working_datetime(next_week_monday + timedelta(days=1))
                current_try_start_dt = candidate
                continue

            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                if reasons is not None:
                    reasons.append(f"Calcul de fin infini à partir de {current_try_start_dt}")
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt + timedelta(days=1))
                continue

            if potential_end_dt > latest_end_dt:
                if reasons is not None:
                    reasons.append(f"Fin {potential_end_dt} > borne {latest_end_dt}")
                return None, None

            if not self._can_add_slot_in_week(current_try_start_dt, potential_end_dt):
                wk = self._relative_week_index(current_try_start_dt)
                allowed = self._allowed_hours_for_week(current_try_start_dt)
                used = self.weekly_load_hours[wk]
                dist = self._weekly_hours_distribution(current_try_start_dt, potential_end_dt)
                add_hours = dist.get(wk, 0)
                if reasons is not None:
                    reasons.append(f"Capacité insuffisante semaine {wk}: dispo {allowed-used:.2f}h, besoin {add_hours:.2f}h")
                days_to_next_monday = (7 - current_try_start_dt.weekday()) % 7
                if days_to_next_monday == 0:
                    days_to_next_monday = 7
                next_week_monday = (current_try_start_dt + timedelta(days=days_to_next_monday)).replace(hour=0, minute=0)
                candidate = self._get_next_working_datetime(next_week_monday)
                if candidate <= current_try_start_dt:
                    candidate = self._get_next_working_datetime(next_week_monday + timedelta(days=1))
                current_try_start_dt = candidate
                continue

            is_overlap = False
            wk_start = self._relative_week_index(current_try_start_dt)
            wk_end = self._relative_week_index(potential_end_dt)
            for wk_check in range(wk_start, wk_end + 1):
                for booked_start, booked_end, booked_of_id in self.slots_by_week.get(wk_check, []):
                    if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                        continue
                    if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                        is_overlap = True
                        if reasons is not None:
                            reasons.append(f"Chevauchement avec OF {booked_of_id} ({booked_start}–{booked_end})")
                        current_try_start_dt = self._get_next_working_datetime(booked_end)
                        break
                if is_overlap:
                    break
            if is_overlap:
                continue

            return current_try_start_dt, potential_end_dt

        return None, None

    def book_slot(self, start_dt: datetime, end_dt: datetime, of_id):
        self.clear_schedule_for_of(of_id)
        self.scheduled_slots.append((start_dt, end_dt, of_id))
        self._ensure_planning_start(start_dt)
        wk_s = self._relative_week_index(start_dt)
        wk_e = self._relative_week_index(end_dt)
        for wk in range(wk_s, wk_e + 1):
            self.slots_by_week[wk].append((start_dt, end_dt, of_id))
        self._register_slot_in_week_load(start_dt, end_dt)

    def clear_schedule_for_of(self, of_id):
        if not self.scheduled_slots:
            return
        to_remove = [(s, e, o) for (s, e, o) in self.scheduled_slots if o == of_id]
        if not to_remove:
            return
        self.scheduled_slots = [(s, e, o) for (s, e, o) in self.scheduled_slots if o != of_id]
        for s, e, _ in to_remove:
            self._ensure_planning_start(s)
            wk_s = self._relative_week_index(s)
            wk_e = self._relative_week_index(e)
            for wk in range(wk_s, wk_e + 1):
                bucket = self.slots_by_week.get(wk)
                if bucket:
                    self.slots_by_week[wk] = [(bs, be, bo) for bs, be, bo in bucket if bo != of_id]
            dist = self._weekly_hours_distribution(s, e)
            for wk, hours in dist.items():
                self.weekly_load_hours[wk] = max(0.0, self.weekly_load_hours[wk] - hours)
                if self.is_bottleneck:
                    cap = float(self.weekly_capacity_by_week.get(wk, 0.0))
                    self.weekly_remaining_capacity[wk] = min(
                        cap,
                        self.weekly_remaining_capacity.get(wk, 0.0) + hours
                    )

    def __repr__(self):
        return (
            f"Post(id={self.id}, name='{self.name}', "
            f"goulot={1 if self.is_bottleneck else 0}, "
            f"unavailable_periods={len(self.unavailable_periods)}, "
            f"scheduled_slots={len(self.scheduled_slots)})"
        )


# classes pour les opérations avec alternatives
from dataclasses import dataclass

@dataclass(slots=True)
class OperationAlternative:
    post_id: str
    standard_time_hours: float
    priority: int

@dataclass(slots=True)
class OperationStep:
    sequence: int
    operation_name: str
    alternatives: list   


# GROUPING ALGORITHM 
def build_bom_graph(bom_data):
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

    ofs_by_id = {of.id: of for of in all_ofs}
    ofs_by_product = defaultdict(list)
    for of in all_ofs:
        ofs_by_product[of.product_id].append(of)

    unassigned_ids = {of.id for of in all_ofs if of.assigned_group_id is None}

    group_counter = 1
    groups = []
    skipped = set()

    while unassigned_ids:
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

        raw_candidates = []
        for pid in family:
            for of in ofs_by_product.get(pid, []):
                if of.id in unassigned_ids and window_start <= of.need_date <= window_end:
                    raw_candidates.append(of)

        cand_pids_raw = {of.product_id for of in raw_candidates}
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

        candidates_sorted = sorted(candidates, key=lambda o: (-get_level(o), o.need_date, o.product_id))
        for ofx in candidates_sorted:
            if ofx.id == anchor_of.id:
                continue
            current_group.add_of(ofx, ps_quantity_change=0)
            unassigned_ids.discard(ofx.id)

        unassigned_ids.discard(anchor_of.id)

        all_ofs_in_group = [anchor_of] + [ofx for ofx in candidates_sorted if ofx.id != anchor_of.id]
        numeric_priorities = [of.priority for of in all_ofs_in_group if of.priority is not None]
        if numeric_priorities:
            group_priority = min(numeric_priorities)
            for of in all_ofs_in_group:
                of.priority = group_priority

        current_group.calculate_consumption(bom_data)

        groups.append(current_group)
        group_counter += 1

    return groups, all_ofs


# SMOOTHING AND SCHEDULING 
def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    from collections import defaultdict
    import bisect
    import heapq
    import time
    import json
    import os
    from datetime import datetime, timedelta, time
    import csv

    max_gap_hours = params.get("max_gap_between_ops_hours")
    if max_gap_hours is not None:
        max_gap_delta = timedelta(hours=max_gap_hours)
    else:
        max_gap_weeks = params.get("max_gap_between_ops_weeks", 2)
        max_gap_delta = timedelta(weeks=max_gap_weeks)
    max_gap_seconds = max_gap_delta.total_seconds()

    week_sort_order = params.get('week_sort_order', 'earliest')

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
        monday = dt_obj.date() - timedelta(days=dt_obj.weekday())
        ws = datetime.combine(monday, time.min)
        we = ws + timedelta(days=7)
        return ws, we

    def candidate_week_starts(need_dt, advance_weeks, retard_weeks, sort_order='earliest'):
        need_monday = need_dt - timedelta(days=need_dt.weekday())
        earliest = need_monday - timedelta(weeks=advance_weeks)
        latest   = need_monday + timedelta(weeks=retard_weeks)
        weeks = []
        cur = earliest
        while cur <= latest:
            weeks.append(cur)
            cur += timedelta(weeks=1)
        if sort_order == 'closest':
            def sort_key(monday):
                diff_weeks = (monday - need_monday).days // 7
                if diff_weeks == 0:
                    return (0, 0)
                elif diff_weeks < 0:
                    return (1, -diff_weeks)
                else:
                    return (2, diff_weeks)
            weeks.sort(key=sort_key)
        else:
            weeks.sort()
        return weeks

    # Precompute product levels
    product_level = {}
    for b in bom_data:
        p = b.parent_product_id
        c = b.child_product_id
        if c:
            product_level[c] = max(product_level.get(c, 0), b.child_bom_level or 0)
        if p:
            product_level[p] = max(product_level.get(p, 0), b.parent_bom_level or 0)

    # BOM children mapping
    bom_children = defaultdict(list)
    for b in bom_data:
        bom_children[b.parent_product_id].append((b.child_product_id, b.quantity_child_per_parent))

    # Global lot management
    global_lots = defaultdict(list) 

    def check_component_availability(prod_norm, qty_parent, ignore_of_id=None):
        children = bom_children.get(prod_norm, [])
        if not children:
            return True, None, {}, ""
        allocations = {}
        latest_ready = None
        for child_norm, coef in children:
            needed = qty_parent * coef
            if needed <= 0:
                continue
            heap = global_lots.get(child_norm, [])
            if not heap:
                return False, None, {}, f"Stock insuffisant pour {child_norm}"
            tmp_heap = heap[:]
            heapq.heapify(tmp_heap)
            taken = []
            remaining = needed
            while remaining > 0 and tmp_heap:
                end_dt, qty_free, of_id = heapq.heappop(tmp_heap)
                if ignore_of_id and of_id == ignore_of_id:
                    continue
                take = min(qty_free, remaining)
                if take > 0:
                    taken.append((end_dt, take, of_id))
                    remaining -= take
                    if remaining <= 1e-9:
                        if latest_ready is None or end_dt > latest_ready:
                            latest_ready = end_dt
                        break
            if remaining > 1e-9:
                return False, None, {}, f"Stock insuffisant pour {child_norm}"
            allocations[child_norm] = taken
        return True, latest_ready, allocations, ""

    def commit_allocations(allocations):
        for child_norm, taken_list in allocations.items():
            heap = global_lots.get(child_norm, [])
            new_heap = []
            for end_dt, qty_free, of_id in heap:
                used = 0
                for t_end_dt, t_qty, t_of_id in taken_list:
                    if t_of_id == of_id and abs((t_end_dt - end_dt).total_seconds()) < 1:
                        used += t_qty
                qty_free -= used
                if qty_free > 0:
                    new_heap.append((end_dt, qty_free, of_id))
            heapq.heapify(new_heap)
            global_lots[child_norm] = new_heap

    def add_produced_lot(prod_norm, end_dt, qty, of_id):
        heapq.heappush(global_lots[prod_norm], (end_dt, qty, of_id))

    # Caches
    _next_working_cache = {}
    _slot_search_cache = {} 

    def get_next_working_datetime_cached(post, dt):
        key = (post.id, dt.year, dt.month, dt.day, dt.hour)
        if key in _next_working_cache:
            return _next_working_cache[key]
        res = post._get_next_working_datetime(dt)
        if len(_next_working_cache) < 10000:
            _next_working_cache[key] = res
        return res

    def find_slot_cached(post, start_search, duration_hours, of_id_to_ignore):
        return post.find_available_slot(start_search, duration_hours, of_id_to_ignore)

    def get_operations(of_obj):
        key_of = of_obj.normalized_id
        key_prod = of_obj.product_id
        key_type = of_obj.product_type.upper()
        return (operations_map.get(key_of) or
                operations_map.get(key_prod) or
                operations_map.get(key_type, []))

    def clear_of_schedules(of_id, ops_steps):
        for step in ops_steps:
            for alt in step.alternatives:
                post = posts_map.get(alt.post_id)
                if post:
                    post.clear_schedule_for_of(of_id + "_" + step.operation_name)

    # Variables globales pour le contexte de groupe 
    group_post_last_end = {}
    temp_post_end = {}

    def try_schedule_step(step, alt, post, start_search, chain_last_end, max_gap_seconds,
                          latest_allowed, of_id, group_context=False):
        candidate_start = start_search
        if chain_last_end is not None:
            candidate_start = max(candidate_start, chain_last_end)

        if group_context:
            real_last = group_post_last_end.get(post.id)
            tent_last = temp_post_end.get(post.id)
            last_for_post = max([d for d in (real_last, tent_last) if d is not None], default=None)
            if last_for_post is not None:
                candidate_start = max(candidate_start, last_for_post)

        candidate_start = get_next_working_datetime_cached(post, candidate_start)

        s_dt, e_dt = find_slot_cached(
            post, candidate_start, alt.standard_time_hours,
            of_id + "_" + step.operation_name
        )

        if not s_dt or not e_dt:
            return None
        if chain_last_end is not None and (s_dt - chain_last_end).total_seconds() > max_gap_seconds:
            return None
        if e_dt > latest_allowed:
            return None
        return s_dt, e_dt

    def select_best_alternative(step, context):
        for alt in step.alternatives:
            post = posts_map.get(alt.post_id)
            if not post:
                continue
            result = try_schedule_step(
                step, alt, post,
                start_search=context['start_search'],
                chain_last_end=context['chain_last_end'],
                max_gap_seconds=context['max_gap_seconds'],
                latest_allowed=context['latest_allowed'],
                of_id=context['of_id'],
                group_context=context.get('group_context', False)
            )
            if result:
                return alt, post, result[0], result[1]
        return None

    smoothing_items = []
    scheduled_ofs = []

    def _make_failure_item(of_obj, group_id_str, status, debug_msg, ops_list=None):
        need_dt = of_obj.need_date
        return {
            "of_id": of_obj.id,
            "product_id": of_obj.raw_product_id,
            "designation": of_obj.designation,
            "group_id": group_id_str,
            "qty_besoin": qty_besoin_raw(of_obj),
            "need_date": need_dt.strftime("%Y-%m-%d"),
            "scheduled_start": None,
            "scheduled_end": None,
            "status": status,
            "retard_jours": 0,
            "avance_jours": 0,
            "operations": ops_list or [],
            "debug": debug_msg,
        }

    def _schedule_of_core(of_to_schedule, group_id_str,
                          group_context=False,
                          gp_last_end=None, tmp_post_end=None):

        need_dt = of_to_schedule.need_date
        advance_w = get_advance_weeks(of_to_schedule)
        retard_w = get_retard_weeks(of_to_schedule)
        earliest_allowed = need_dt - timedelta(weeks=advance_w)
        latest_allowed = need_dt + timedelta(weeks=retard_w)

        prod_norm = of_to_schedule.product_id
        qty = of_to_schedule.quantity

        stock_ok, components_ready_dt, allocations, stock_reason = check_component_availability(
            prod_norm, qty, ignore_of_id=of_to_schedule.id
        )
        if not stock_ok:
            status = "ÉCHOUÉ(stock insuffisant)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None
            smoothing_items.append(_make_failure_item(of_to_schedule, group_id_str, status, stock_reason))
            scheduled_ofs.append(of_to_schedule)
            return of_to_schedule

        ops = get_operations(of_to_schedule)
        if not ops:
            status = "ÉCHOUÉ(poste indispo)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None
            smoothing_items.append(_make_failure_item(of_to_schedule, group_id_str, status, "No operations"))
            scheduled_ofs.append(of_to_schedule)
            return of_to_schedule

        clear_of_schedules(of_to_schedule.id, ops)

        week_starts = candidate_week_starts(need_dt, advance_w, retard_w, week_sort_order)
        chosen_sched = None
        chosen_tmp_post_end = {}

        for ws in week_starts:
            if ws > latest_allowed:
                break
            start_search = max(ws, earliest_allowed)
            if components_ready_dt is not None:
                start_search = max(start_search, components_ready_dt)

            chain_last_end = None
            temp_sched = []
            iter_tmp_post_end = {}
            ok = True
            for step in ops:
                context = {
                    'start_search': start_search,
                    'chain_last_end': chain_last_end,
                    'max_gap_seconds': max_gap_seconds,
                    'latest_allowed': latest_allowed,
                    'of_id': of_to_schedule.id,
                    'group_context': group_context,
                }
                if group_context and gp_last_end is not None:
                    group_post_last_end.clear()
                    group_post_last_end.update(gp_last_end)
                if group_context and tmp_post_end is not None:
                    temp_post_end.clear()
                    temp_post_end.update(iter_tmp_post_end)
                selected = select_best_alternative(step, context)
                if not selected:
                    ok = False
                    break
                alt, post, s_dt, e_dt = selected
                temp_sched.append((step, post, s_dt, e_dt))
                chain_last_end = e_dt
                iter_tmp_post_end[post.id] = e_dt
                start_search = e_dt
            if ok and temp_sched:
                chosen_sched = temp_sched
                chosen_tmp_post_end = iter_tmp_post_end
                break

        if chosen_sched:
            for step, post, s_dt, e_dt in chosen_sched:
                post.book_slot(s_dt, e_dt, of_to_schedule.id + "_" + step.operation_name)
            start_dt = chosen_sched[0][2]
            end_dt = chosen_sched[-1][3]
            of_to_schedule.scheduled_start_date = start_dt
            of_to_schedule.scheduled_end_date = end_dt
            if start_dt.date() <= need_dt.date():
                status = "OUI"
            elif need_dt.date() < start_dt.date() <= latest_allowed.date():
                status = "NON"
            else:
                status = "ÉCHOUÉ"
            of_to_schedule.status = status
            commit_allocations(allocations)
            if qty > 0:
                add_produced_lot(prod_norm, end_dt, qty, of_to_schedule.id)

            if group_context and gp_last_end is not None:
                for pid, enddt in chosen_tmp_post_end.items():
                    if gp_last_end.get(pid) is None or enddt > gp_last_end[pid]:
                        gp_last_end[pid] = enddt

            retard_jours = days_delay_if_late(end_dt, need_dt) if status == "NON" else 0
            avance_jours = (need_dt - start_dt).days if start_dt < need_dt else 0

            smoothing_items.append({
                "of_id": of_to_schedule.id,
                "product_id": of_to_schedule.raw_product_id,
                "designation": of_to_schedule.designation,
                "group_id": group_id_str,
                "qty_besoin": qty_besoin_raw(of_to_schedule),
                "need_date": need_dt.strftime("%Y-%m-%d"),
                "scheduled_start": dt_to_str(start_dt),
                "scheduled_end": dt_to_str(end_dt),
                "status": status,
                "retard_jours": retard_jours,
                "avance_jours": avance_jours,
                "operations": [
                    {
                        "operation": step.operation_name,
                        "post_id": post.id,
                        "start": dt_to_str(s_dt),
                        "end": dt_to_str(e_dt),
                    }
                    for step, post, s_dt, e_dt in chosen_sched
                ],
            })
        else:
            status = "ÉCHOUÉ(poste indispo)"
            of_to_schedule.status = status
            of_to_schedule.scheduled_start_date = None
            of_to_schedule.scheduled_end_date = None
            smoothing_items.append(
                _make_failure_item(of_to_schedule, group_id_str, status, "No slot within allowed weeks")
            )

        scheduled_ofs.append(of_to_schedule)
        return of_to_schedule

    def schedule_single_of(of_to_schedule, group_id=None):
        gid = group_id if group_id else "INDIVIDUEL"
        return _schedule_of_core(of_to_schedule, gid, group_context=False)

    parent_to_children = defaultdict(set)
    for b in bom_data:
        p = b.parent_product_id
        c = b.child_product_id
        if p and c:
            parent_to_children[p].add(c)

    planning_queue = []
    for group in groups:
        planning_queue.append(('group', group, group.time_window_start))
    for of in all_ofs_with_groups:
        if of.assigned_group_id is None:
            planning_queue.append(('individual', of, of.need_date))

    def sort_key(item):
        item_type, obj, _ = item
        if item_type == 'group':
            group_priority = obj.ofs[0].priority if obj.ofs else None
            level = -product_level.get(obj.ps_product_id, 0)
        else:
            group_priority = obj.priority
            level = -product_level.get(obj.product_id, 0)
        return (
            group_priority is None,
            group_priority if group_priority is not None else float('inf'),
            level,
            item[2]
        )

    planning_queue.sort(key=sort_key)

    group_post_last_end.clear()
    temp_post_end.clear()

    for item_type, obj, _ in planning_queue:
        if item_type == 'group':
            group = obj
            group_ofs = [of for of in all_ofs_with_groups if of.assigned_group_id == group.id]
            product_to_ofs = defaultdict(list)
            for of in group_ofs:
                product_to_ofs[of.product_id].append(of)
            for lst in product_to_ofs.values():
                lst.sort(key=lambda o: (o.need_date, o.id))
            product_level_local = {}
            for pn, ofs in product_to_ofs.items():
                product_level_local[pn] = max(product_level.get(pn, 0) for _ in ofs)
            ordered_products = sorted(product_to_ofs.keys(), key=lambda pn: -product_level_local.get(pn, 0))
            visited = set()
            ofs_sorted = []
            def dfs(pn):
                for of in product_to_ofs[pn]:
                    if of.id not in visited:
                        ofs_sorted.append(of)
                        visited.add(of.id)
                for child in parent_to_children.get(pn, set()):
                    if child in product_to_ofs:
                        dfs(child)
            for pn in ordered_products:
                dfs(pn)

            for of_to_schedule in ofs_sorted:
                _schedule_of_core(
                    of_to_schedule,
                    group_id_str=group.id,
                    group_context=True,
                    gp_last_end=group_post_last_end,
                    tmp_post_end=temp_post_end,
                )
        else:
            of_to_schedule = obj
            schedule_single_of(of_to_schedule)

    smoothing_json_path = params.get("smoothing_json_path")
    if smoothing_json_path:
        out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "items": smoothing_items}
        try:
            with open(smoothing_json_path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Smoothing] JSON write error: {e}")

    smoothing_csv_path = params.get("smoothing_csv_path")
    if smoothing_csv_path:
        try:
            write_smoothing_csv(smoothing_items, smoothing_csv_path)
        except Exception as e:
            print(f"[Smoothing] CSV report error: {e}")

    weekly_capacity_report_path = params.get("weekly_capacity_report_path")
    if weekly_capacity_report_path:
        try:
            write_posts_weekly_capacity_report(posts_map, weekly_capacity_report_path)
        except Exception as e:
            print(f"[Smoothing] Weekly capacity report error: {e}")

    final_by_id = {of.id: of for of in scheduled_ofs}
    updated_all = [final_by_id.get(orig.id, orig) for orig in all_ofs_with_groups]

    return updated_all


# OUTPUT WRITERS 
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
        "Priority",         
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

                priority_str = str(of_obj.priority) if of_obj.priority is not None else ""

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
                        priority_str,          
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

                priority_str = str(of_obj.priority) if of_obj.priority is not None else ""

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
                        priority_str,         
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

    header = ["Groupe", "OF", "Date de besoin", "Debut", "Fin", "Statut"]
    with open(output_filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(header)
        for item in smoothing_items:
            group_id = item.get("group_id", "INDIVIDUEL")
            of_id = item.get("of_id", "")
            need_date = item.get("need_date", "")
            start = item.get("scheduled_start", "")
            end = item.get("scheduled_end", "")
            status = item.get("status", "")
            writer.writerow([group_id, of_id, need_date, start, end, status])
    print(f"✅ Fichier CSV du lissage généré (avec début/fin) : {output_filepath}")


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

            first = post._first_week_index if post._first_week_index is not None else 1
            last = post._last_week_index if post._last_week_index is not None else max(post.weekly_load_hours.keys()) if post.weekly_load_hours else 1

            for wk_index in range(first, last+1):
                planned = post.weekly_load_hours.get(wk_index, 0.0)
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


# LOADERS 
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
        "priorite": ["priorite", "priority", "priorité"], 
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

        a_hit = None
        for k in ["Avance"] + ALIASES.get("avance", []):
            if k.lower() in lower:
                a_hit = lower[k.lower()]
                break
        out["_AVANCE_OPT_"] = a_hit

        p_hit = None
        for k in ["Priorite"] + ALIASES.get("priorite", []):
            if k.lower() in lower:
                p_hit = lower[k.lower()]
                break
        out["_PRIORITE_OPT_"] = p_hit

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

                advance_val = None
                a_col = mapped_cols.get("_AVANCE_OPT_")
                if a_col:
                    advance_val = row.get(a_col)

                priorite_val = None
                p_col = mapped_cols.get("_PRIORITE_OPT_")
                if p_col:
                    raw_prior = row.get(p_col)
                    if raw_prior is not None and str(raw_prior).strip() != "":
                        try:
                            priorite_val = int(float(raw_prior))
                        except (ValueError, TypeError):
                            priorite_val = None

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
                    priority=priorite_val,          
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
        required_cols_posts = ["PostID", "PostName", "WeekStart", "CapacityHours"]

        f_posts, reader_posts, used_delim_posts, used_enc_posts = _make_reader(
            filepath_posts, required_cols=None, fallback=","
        )
        if not reader_posts or not reader_posts.fieldnames:
            raise FileNotFoundError(f"Posts CSV {filepath_posts} appears empty or has no header.")

        lower = {c.strip().lower(): c.strip() for c in reader_posts.fieldnames}
        colmap = {}
        for col in required_cols_posts:
            if col.lower() in lower:
                colmap[col] = lower[col.lower()]
            else:
                raise ValueError(
                    f"Missing column '{col}' in posts CSV. Found: {reader_posts.fieldnames}"
                )

        goulot_col = None
        for c in reader_posts.fieldnames:
            if c.strip().lower() in ("goulot", "bottleneck"):
                goulot_col = c.strip()
                break

        def parse_goulot(v):
            s = str(v or "").strip().lower()
            return s not in ("0", "non", "false", "no", "n")

        raw_capacities = defaultdict(list)   
        post_names = {}
        post_goulot = {}
        all_mondays = []

        for row in reader_posts:
            raw_pid = row[colmap["PostID"]]
            pid = norm_code(raw_pid)
            name = row[colmap["PostName"]]
            post_names[pid] = name

            is_bottleneck = True
            if goulot_col and goulot_col in row:
                is_bottleneck = parse_goulot(row[goulot_col])
            post_goulot[pid] = is_bottleneck

            week_str = row[colmap["WeekStart"]]
            try:
                week_date = datetime.strptime(week_str, "%Y-%m-%d").date()
            except ValueError:
                print(f"  [!] Invalid date '{week_str}' for post {pid}, skipping row")
                continue

            cap_str = row[colmap["CapacityHours"]]
            try:
                cap = float(try_parse_float(cap_str))
            except Exception:
                print(f"  [!] Invalid capacity '{cap_str}' for post {pid}, skipping row")
                continue

            raw_capacities[pid].append((week_date, cap))
            all_mondays.append(week_date)

        if f_posts:
            f_posts.close()

        if not raw_capacities:
            print("Warning: No valid post capacity data found.")
            return posts_map, {}

        base_monday = min(all_mondays)
        print(f"  Base Monday (week 1) for posts: {base_monday}")

        for pid, capacities in raw_capacities.items():
            weekly_cap = {}
            for monday, cap in capacities:
                week_idx = 1 + (monday - base_monday).days // 7
                weekly_cap[week_idx] = cap

            post = Post(
                id=pid,
                name=post_names.get(pid, pid),
                weekly_capacity_by_week=weekly_cap,
                is_bottleneck=post_goulot.get(pid, True),
            )
            post.set_week0_monday(base_monday)
            posts_map[pid] = post

        print(f"Loaded {len(posts_map)} posts (delimiter='{used_delim_posts}', encoding='{used_enc_posts}').")

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

        raw_alternatives = defaultdict(list)
        for row in reader_ops:
            raw_key = row.get(colmap_ops["ProductID"]) or row.get("ProductType") or "UNKNOWN_OP_KEY"
            key = norm_code(raw_key)
            if key == "UNKNOWN_OP_KEY" or not key:
                continue

            op_name = row[colmap_ops["OperationName"]]
            seq_str = row.get(colmap_ops["Sequence"], "0") or "0"
            sequence = int(seq_str)
            post_id = norm_code(row.get(colmap_ops["PostID"], ""))
            hours = try_parse_float(row[colmap_ops["StandardTimeHours"]])
            priority = int(row.get(colmap_ops["Priority"], "1") or "1")

            raw_alternatives[(key, sequence, op_name)].append((post_id, hours, priority))

        for (key, seq, op_name), alt_list in raw_alternatives.items():
            alt_list.sort(key=lambda x: x[2])
            alternatives = [OperationAlternative(pid, hrs, prio) for pid, hrs, prio in alt_list]
            operations_map[key].append(OperationStep(seq, op_name, alternatives))

        for key in operations_map:
            operations_map[key].sort(key=lambda step: step.sequence)

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
                        if len(parts) >= 10:
                            _, of_id, designation, product_id, fg, cat, us, fs, qty, need_date = parts[:10]
                            priority_val = None
                            if len(parts) >= 11:
                                try:
                                    priority_val = int(float(parts[10]))
                                except (ValueError, TypeError):
                                    priority_val = None
                        else:
                            continue

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
                                priority=priority_val,   
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


# MAIN
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
        "max_gap_between_ops_hours": 336,
        'week_sort_order': 'closest'
    }

    groups, all_ofs_with_groups = run_grouping_algorithm(all_ofs, bom_data, HORIZON_H_WEEKS)

    all_ofs_scheduled = smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params)

    write_grouped_needs_to_file(output_file, groups, all_ofs_scheduled)
    print(f"\nDone -> {output_file}")