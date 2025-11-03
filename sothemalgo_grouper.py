from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import calendar
import csv
import os

# --- Configuration & Parameters ---
HORIZON_H_MONTHS = 2
HORIZON_H_WEEKS = 10
POST_DEFAULT_CAPACITY_HOURS_WEEK = 35
ADVANCE_RETREAT_WEEKS = 3

def try_parse_float(value):
    """
    Convert numeric strings that may use locale-specific separators into float.
    Raises ValueError when conversion is not possible.
    """
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

# --- Data Structures ---
class ManufacturingOrder:
    def __init__(self, id, designation, product_id, product_type, bom_level, need_date_str, quantity, fg, cat, us, fs, unit="U", status="UNASSIGNED"):
        self.id = id
        self.designation = designation
        self.product_id = product_id
        self.product_type = product_type
        self.bom_level = int(bom_level)
        try:
            self.need_date = datetime.strptime(need_date_str, "%Y-%m-%d")
        except ValueError:
            try:
                self.need_date = datetime.strptime(need_date_str, "%d/%m/%Y")
            except ValueError:
                try:
                    self.need_date = datetime.strptime(need_date_str, "%d/%m/%y")
                except ValueError:
                    raise ValueError(f"Date format for {need_date_str} not recognized.")
        # on garde la valeur EXACTE du fichier pour la réécriture
        self.source_qty = str(quantity) if quantity is not None else ""
        # on garde aussi la version numérique pour les calculs
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
        # Individual product stock for this specific product line
        self.individual_product_stock = 0

    def __repr__(self):
        return (f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.product_id}', type='{self.product_type}', "
                f"level={self.bom_level}, need={self.need_date.strftime('%Y-%m-%d')}, qty={self.quantity}, "
                f"fg='{self.fg}', cat='{self.cat}', "
                f"indiv_stock={self.individual_product_stock}, "
                f"group={self.assigned_group_id}, status='{self.status}')")

class BOMEntry:
    def __init__(self, parent_product_id, child_product_id, quantity_child_per_parent, child_bom_level):
        self.parent_product_id = parent_product_id
        self.child_product_id = child_product_id
        self.quantity_child_per_parent = try_parse_float(quantity_child_per_parent)
        self.child_bom_level = int(child_bom_level)

    def __repr__(self):
        return (f"BOM(parent='{self.parent_product_id}' uses {self.quantity_child_per_parent} of child='{self.child_product_id}' "
                f"at level {self.child_bom_level})")

class Group:
    def __init__(self, id, ps_product_id, initial_ps_of, window_start_date, window_end_date):
        self.id = id
        self.ps_product_id = ps_product_id
        self.time_window_start = window_start_date
        self.time_window_end = window_end_date
        self.ofs = []
        self.current_ps_stock_available = 0
        self.component_stocks = {}
        
        # Track individual product stock for each OF
        self.individual_product_stocks = {}  # {product_id: group-level remaining stock}
        
        # Track product consumption (diagnostic)
        self.product_consumption = {}  # {product_id: total_consumed_quantity}
        
        self.add_of(initial_ps_of, ps_quantity_change=initial_ps_of.quantity)

    def add_of(self, of_to_add, ps_quantity_change=0):
        self.ofs.append(of_to_add)
        self.current_ps_stock_available += ps_quantity_change
        
        # Update component stocks (balance-style tracker)
        if of_to_add.product_id not in self.component_stocks:
            self.component_stocks[of_to_add.product_id] = 0
        self.component_stocks[of_to_add.product_id] += ps_quantity_change
        
        # Initial fields for per-OF tracking (actual values computed later)
        product_id = of_to_add.product_id
        if product_id not in self.individual_product_stocks:
            self.individual_product_stocks[product_id] = 0
        if product_id not in self.product_consumption:
            self.product_consumption[product_id] = 0

        of_to_add.individual_product_stock = 0
        of_to_add.assigned_group_id = self.id
        of_to_add.status = "ASSIGNED"

    def calculate_consumption(self, bom_data):
        """
        Recalcule les stocks restants par OF avec FIFO, en normalisant violemment les IDs produit.
        """
        from collections import defaultdict, deque

        # --- 1. normalisation super agressive ---
        def norm(x):
            if x is None:
                return ""
            s = str(x)
            s = s.replace('\ufeff', '')  # BOM éventuel
            # enlève TOUS les espaces/blancs (même insécables)
            s = ''.join(s.split())
            s = s.upper()
            return s

        print(f"[CONSUMP] === Calcul consommation pour le groupe {self.id} ===")

        # --- 2. indexer la nomenclature avec IDs normalisés ---
        bom_lookup = defaultdict(list)
        parents = set()
        children = set()
        for bom in bom_data:
            p = norm(bom.parent_product_id)
            c = norm(bom.child_product_id)
            bom_lookup[p].append((c, bom.quantity_child_per_parent))
            parents.add(p)
            children.add(c)

        premix_products = {c for c in children if c not in parents}
        type_priority = {"PS": 0, "SF": 1, "PF": 2}

        # log des OFs du groupe
        print("[CONSUMP] OFs dans le groupe :")
        for of in self.ofs:
            print(f"    - {of.id} | prod={norm(of.product_id)} | qty={of.quantity} | date={of.need_date.strftime('%Y-%m-%d')}")

        # --- 3. ordre de traitement : premix d'abord, puis par niveau/date/type ---
        sorted_ofs = sorted(
            self.ofs,
            key=lambda of: (
                0 if norm(of.product_id) in premix_products else 1,
                of.bom_level,
                of.need_date,
                type_priority.get(of.product_type, 3),
            )
        )

        fifo_supply = defaultdict(deque)   # produit → deque de {of_id, remaining}
        remaining_per_of = {of.id: 0.0 for of in self.ofs}
        product_produced = defaultdict(float)
        product_consumption = defaultdict(float)
        component_balance = defaultdict(float)
        production_status = {}
        EPS = 1e-9

        # --- 4. boucle principale ---
        for of in sorted_ofs:
            prod_id = norm(of.product_id)
            qty = float(of.quantity)

            # besoins composants de CE produit
            components_needed = {}
            for child_id, q_child in bom_lookup.get(prod_id, []):
                need = q_child * qty
                if need > EPS:
                    components_needed[child_id] = components_needed.get(child_id, 0.0) + need

            # check dispo
            can_produce = True
            for comp_id, req in components_needed.items():
                available = sum(e["remaining"] for e in fifo_supply.get(comp_id, []))
                if available + EPS < req:
                    can_produce = False
                    break

            if not can_produce:
                print(f"    -> pas assez de composants pour OF {of.id} ({prod_id}) : NON PRODUIT")
                production_status[of.id] = False
                of.individual_product_stock = 0.0
                remaining_per_of[of.id] = 0.0
                continue

            production_status[of.id] = True

            # consommer FIFO
            for comp_id, req in components_needed.items():
                need_left = req
                print(f"    consommation FIFO pour OF {of.id}: besoin composant {comp_id} = {req:.6f}")
                while need_left > EPS and fifo_supply.get(comp_id):
                    entry = fifo_supply[comp_id][0]
                    take = min(entry["remaining"], need_left)
                    entry["remaining"] -= take
                    need_left -= take
                    remaining_per_of[entry["of_id"]] -= take
                    print(f"        prend {take:.6f} depuis OF {entry['of_id']} (reste sur ce lot={entry['remaining']:.6f})")
                    if entry["remaining"] <= EPS:
                        fifo_supply[comp_id].popleft()
                product_consumption[comp_id] += req
                component_balance[comp_id] -= req

            # produire cet OF
            fifo_supply[prod_id].append({"of_id": of.id, "remaining": qty})
            remaining_per_of[of.id] += qty
            component_balance[prod_id] += qty
            product_produced[prod_id] += qty
            print(f"    => produit {qty} de {prod_id} (lot OF {of.id})")

        # --- 5. répartition finale par produit (FIFO) ---
        for prod_id, total_prod in product_produced.items():
            total_cons = product_consumption.get(prod_id, 0.0)
            must_remain = max(0.0, total_prod - total_cons)

            ofs_of_prod = [of for of in sorted_ofs if norm(of.product_id) == prod_id]
            for of in ofs_of_prod:
                cur = max(0.0, remaining_per_of[of.id])
                if must_remain <= 0:
                    remaining_per_of[of.id] = 0.0
                else:
                    take = min(cur, must_remain)
                    remaining_per_of[of.id] = take
                    must_remain -= take

        # --- 6. écrire dans les OFs ---
        print("\n[CONSUMP] Stocks finaux par OF (c’est CE chiffre qui doit aller dans le fichier) :")
        for of in self.ofs:
            if not production_status.get(of.id, False):
                of.individual_product_stock = 0.0
            else:
                rem = max(0.0, remaining_per_of.get(of.id, 0.0))
                # borne au qty de l’OF
                rem = min(rem, of.quantity)
                of.individual_product_stock = rem
            print(f"    OF {of.id} ({norm(of.product_id)}) => stock restant = {of.individual_product_stock}")

        # agrégats pour le groupe
        self.product_consumption = dict(product_consumption)
        self.individual_product_stocks = {
            pid: sum(
                max(0.0, remaining_per_of[o.id])
                for o in self.ofs
                if norm(o.product_id) == pid
            )
            for pid in {norm(o.product_id) for o in self.ofs}
        }
        self.component_stocks = dict(component_balance)

        print(f"[CONSUMP] === Fin calcul groupe {self.id} ===\n")


class Post:
    def __init__(self, id, name, default_capacity_hours_week=35, 
                 work_start_time_config=time(8, 0), work_end_time_config=time(17, 0), 
                 lunch_start_time_config=time(12,0), lunch_end_time_config=time(13,0)):
        self.id = id
        self.name = name
        
        self.work_start_time = work_start_time_config
        self.work_end_time = work_end_time_config
        self.lunch_start_time = lunch_start_time_config
        self.lunch_end_time = lunch_end_time_config

        # Calculate effective work hours per day
        ws = datetime.combine(date.min, self.work_start_time)
        we = datetime.combine(date.min, self.work_end_time)
        ls = datetime.combine(date.min, self.lunch_start_time)
        le = datetime.combine(date.min, self.lunch_end_time)

        self.daily_capacity_hours = 0
        if we > ws:
            total_work_seconds = (we - ws).total_seconds()
            lunch_seconds = 0
            # Check for a valid lunch break that is within work hours
            if le > ls and ls >= ws and le <= we:
                actual_lunch_start = max(ws, ls)
                actual_lunch_end = min(we, le)
                if actual_lunch_end > actual_lunch_start:
                    lunch_seconds = (actual_lunch_end - actual_lunch_start).total_seconds()
            
            self.daily_capacity_hours = (total_work_seconds - lunch_seconds) / 3600.0
            if self.daily_capacity_hours < 0: self.daily_capacity_hours = 0
        
        self.unavailable_periods = []
        self.scheduled_slots = []

    def add_unavailable_period(self, start_date_str, end_date_str):
        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if end_dt < start_dt:
                print(f"Warning: Invalid unavailability period for post {self.id}: end date is before start date. {start_date_str} - {end_date_str}")
                return
            self.unavailable_periods.append((start_dt, end_dt))
            self.unavailable_periods.sort()
        except ValueError:
            print(f"Warning: Invalid date format for unavailability period for post {self.id}: {start_date_str}-{end_date_str}")

    def _is_working_moment(self, dt_obj):
        if dt_obj.weekday() >= 5:
            return False
        
        current_time = dt_obj.time()
        if not (self.work_start_time <= current_time < self.work_end_time):
            return False
        
        if self.lunch_start_time <= current_time < self.lunch_end_time:
            return False
        
        for un_start, un_end in self.unavailable_periods:
            if un_start <= dt_obj <= un_end:
                return False
        return True

    def _get_next_working_datetime(self, current_dt_orig):
        current_dt = current_dt_orig
        max_iterations = 10000
        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            current_dt = current_dt.replace(second=0, microsecond=0)

            while True:
                date_changed = False
                if current_dt.weekday() >= 5:
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                    date_changed = True
                    continue

                is_unavailable_day = False
                for un_start, un_end in self.unavailable_periods:
                    if un_start.date() <= current_dt.date() <= un_end.date():
                        if current_dt < un_end:
                             current_dt = (un_end + timedelta(minutes=1))
                             current_dt = current_dt.replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                             date_changed = True
                             is_unavailable_day = True
                             break
                if is_unavailable_day:
                    continue

                break

            current_time = current_dt.time()

            if current_time >= self.work_end_time:
                current_dt = (current_dt + timedelta(days=1)).replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                continue

            if current_time < self.work_start_time:
                current_dt = current_dt.replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)

            current_time = current_dt.time()

            if self.lunch_start_time <= current_time < self.lunch_end_time:
                current_dt = current_dt.replace(hour=self.lunch_end_time.hour, minute=self.lunch_end_time.minute)
                continue

            is_currently_unavailable = False
            for un_start, un_end in self.unavailable_periods:
                 if un_start <= current_dt < un_end:
                      current_dt = un_end
                      is_currently_unavailable = True
                      break
            if is_currently_unavailable:
                 continue

            if self._is_working_moment(current_dt):
                return current_dt
            
            current_dt += timedelta(minutes=1)

        print(f"Warning: Post {self.id} _get_next_working_datetime exceeded max iterations from {current_dt_orig}. Returning original.")
        return current_dt_orig

    def calculate_end_datetime(self, start_dt_param, duration_hours):
        if duration_hours <= 0:
            return start_dt_param

        actual_start_dt = self._get_next_working_datetime(start_dt_param)
        
        current_dt = actual_start_dt
        remaining_seconds = duration_hours * 3600
        
        max_calc_iterations = 20000
        calc_iter = 0

        while remaining_seconds > 0 and calc_iter < max_calc_iterations:
            calc_iter += 1
            if not self._is_working_moment(current_dt):
                current_dt = self._get_next_working_datetime(current_dt)
                if current_dt == self._get_next_working_datetime(current_dt + timedelta(microseconds=1)) and self._is_working_moment(current_dt) == False:
                    print(f"Error: Post {self.id} calculate_end_datetime stuck finding next working moment from {current_dt}.")
                    return datetime.max
                continue

            next_minute_dt = current_dt + timedelta(minutes=1)
            
            if self._is_working_moment(current_dt):
                seconds_this_minute = 60
                can_consume_seconds = min(remaining_seconds, seconds_this_minute)
                remaining_seconds -= can_consume_seconds
                current_dt = next_minute_dt
            else:
                current_dt = self._get_next_working_datetime(current_dt)

        if remaining_seconds > 0:
            print(f"Warning: Post {self.id} calculate_end_datetime could not schedule full duration. Remaining: {remaining_seconds/3600} hrs.")
            return datetime.max

        return current_dt

    def find_available_slot(self, search_start_dt_param, duration_hours, of_id_to_ignore=None):
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        
        max_search_datetime = search_start_dt_param + timedelta(days=180)

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)

            if potential_end_dt == datetime.max:
                current_try_start_dt = (current_try_start_dt + timedelta(days=1)).replace(
                    hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt)
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

        print(f"Warning: Slot search for post {self.id} exceeded search limit from {search_start_dt_param} for {duration_hours}hr task.")
        return None, None
    
    def book_slot(self, start_dt, end_dt, of_id):
        self.clear_schedule_for_of(of_id)
        self.scheduled_slots.append((start_dt, end_dt, of_id))
        self.scheduled_slots.sort()

    def clear_schedule_for_of(self, of_id):
        self.scheduled_slots = [(s, e, o) for s, e, o in self.scheduled_slots if o != of_id]

    def __repr__(self):
        return f"Post(id={self.id}, name='{self.name}', daily_hours={self.daily_capacity_hours:.2f}, unavailable_periods={len(self.unavailable_periods)}, scheduled_slots={len(self.scheduled_slots)})"

class Operation:
    def __init__(self, product_key, operation_name, post_id, standard_time_hours, sequence, priority):
        self.product_key = product_key
        self.operation_name = operation_name
        self.post_id = post_id
        self.standard_time_hours = try_parse_float(standard_time_hours)
        self.sequence = sequence
        self.priority = priority

# --- Helper Functions ---
def detect_csv_delimiter(filepath, fallback=','):
    """
    Inspect the first non-empty line of a CSV-like file to infer its delimiter.
    Returns the detected delimiter or the provided fallback when no clear candidate is found.
    """
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            for line in f:
                sample = line.strip()
                if not sample:
                    continue
                potential_delims = ['\t', ';', ',', '|']
                delim_counts = {delim: sample.count(delim) for delim in potential_delims}
                best_delim, best_count = max(delim_counts.items(), key=lambda item: item[1])
                if best_count > 0:
                    return best_delim
                break
    except FileNotFoundError:
        pass
    return fallback

def find_qty_of_component_in_product(product_to_make_id, component_to_find_id, bom_data, memo=None):
    if memo is None: memo = {}
    if (product_to_make_id, component_to_find_id) in memo:
        return memo[(product_to_make_id, component_to_find_id)]

    if product_to_make_id == component_to_find_id: return 1.0

    total_component_needed = 0.0
    direct_components = [b for b in bom_data if b.parent_product_id == product_to_make_id]

    for bom_line in direct_components:
        qty_in_child = find_qty_of_component_in_product(bom_line.child_product_id, component_to_find_id, bom_data, memo)
        total_component_needed += bom_line.quantity_child_per_parent * qty_in_child
            
    memo[(product_to_make_id, component_to_find_id)] = total_component_needed
    return total_component_needed

def sort_ofs_for_grouping(of_list):
    return sorted(of_list, key=lambda of: (of.designation, -of.bom_level, of.need_date))

# --- Main Grouping Algorithm ---
def run_grouping_algorithm(all_ofs, bom_data, horizon_H_weeks_param):
    group_counter = 1
    groups = []
    
    while True:
        unassigned_client_ofs = sorted(
            [of for of in all_ofs if of.product_type in ["PF", "SF"] and of.assigned_group_id is None],
            key=lambda of: (-of.bom_level, of.need_date, of.designation)
        )

        if not unassigned_client_ofs: break

        base_client_of = unassigned_client_ofs[0]
        
        needed_components = {}
        family_product_ids = {base_client_of.product_id}
        for bom_entry in bom_data:
            qty_needed = find_qty_of_component_in_product(base_client_of.product_id, bom_entry.child_product_id, bom_data)
            if qty_needed > 0:
                total_qty_needed = qty_needed * base_client_of.quantity
                needed_components[bom_entry.child_product_id] = needed_components.get(bom_entry.child_product_id, 0) + total_qty_needed
                family_product_ids.add(bom_entry.child_product_id)
        
        best_supply_candidate = None
        best_date_diff = float('inf')
        for comp_id in needed_components.keys():
            candidate_supply = [
                of for of in all_ofs
                if of.product_id == comp_id and of.assigned_group_id is None
            ]
            if candidate_supply:
                closest_supply = min(candidate_supply, key=lambda x: abs((x.need_date - base_client_of.need_date).days))
                date_diff = abs((closest_supply.need_date - base_client_of.need_date).days)
                if date_diff < best_date_diff:
                    best_date_diff = date_diff
                    best_supply_candidate = closest_supply
        
        if best_supply_candidate:
            main_premix = best_supply_candidate.product_id
            reference_date = best_supply_candidate.need_date
        else:
            main_premix = f"PS_GROUP_{group_counter}"
            reference_date = base_client_of.need_date
        
        child_dates = []
        for comp_id in needed_components.keys():
            candidate_children = [
                of for of in all_ofs
                if of.product_id == comp_id and of.assigned_group_id is None
            ]
            if candidate_children:
                earliest_child = min(candidate_children, key=lambda x: x.need_date)
                child_dates.append(earliest_child.need_date)
        
        if child_dates:
            window_start_date = min(child_dates)
        else:
            window_start_date = reference_date
        window_duration_td = timedelta(weeks=horizon_H_weeks_param)
        window_end_date = window_start_date + window_duration_td - timedelta(days=1)
        
        current_group = Group(f"GRP{group_counter}", main_premix, base_client_of, window_start_date, window_end_date)
        
        for comp_id, qty_needed in needed_components.items():
            current_group.component_stocks[comp_id] = -qty_needed

        print(f"Created {current_group} with client OF {base_client_of.id}, window start {window_start_date.strftime('%Y-%m-%d')}, horizon {horizon_H_weeks_param}w")

        available_ps_ofs = [
            of for of in all_ofs 
            if of.product_type == "PS" and 
               of.assigned_group_id is None and
               window_start_date <= of.need_date <= window_end_date
        ]
        
        for ps_of in sorted(available_ps_ofs, key=lambda o: o.need_date):
            if ps_of.product_id in needed_components:
                current_group.add_of(ps_of, ps_quantity_change=ps_of.quantity)
                current_group.component_stocks[ps_of.product_id] += ps_of.quantity
                family_product_ids.add(ps_of.product_id)
                print(f"  Added Premix OF {ps_of.id} ({ps_of.product_id}) to {current_group.id}")

        other_client_ofs = [
            of for of in all_ofs 
            if of.product_type in ["PF", "SF"] and 
               of.assigned_group_id is None and
               of.id != base_client_of.id and
               window_start_date <= of.need_date <= window_end_date
        ]
        
        for client_of in sorted(other_client_ofs, key=lambda o: o.need_date):
            client_needed_components = {}
            for bom_entry in bom_data:
                qty_needed = find_qty_of_component_in_product(client_of.product_id, bom_entry.child_product_id, bom_data)
                if qty_needed > 0:
                    total_needed = qty_needed * client_of.quantity
                    client_needed_components[bom_entry.child_product_id] = client_needed_components.get(bom_entry.child_product_id, 0) + total_needed
            
            is_direct_component = client_of.product_id in family_product_ids
            shared_components = any(comp_id in family_product_ids for comp_id in client_needed_components.keys())
            same_family = is_direct_component or shared_components
            
            if same_family:
                current_group.add_of(client_of, ps_quantity_change=0)
                
                if client_of.product_type == "SF":
                    current_group.component_stocks[client_of.product_id] = current_group.component_stocks.get(client_of.product_id, 0) + client_of.quantity
                
                for comp_id, qty_needed in client_needed_components.items():
                    current_group.component_stocks[comp_id] = current_group.component_stocks.get(comp_id, 0) - qty_needed
                    needed_components[comp_id] = needed_components.get(comp_id, 0) + qty_needed
                
                family_product_ids.add(client_of.product_id)
                family_product_ids.update(client_needed_components.keys())
                    
                print(f"  Added family OF {client_of.id} ({client_of.product_type}) to {current_group.id}")
        
        # Calculate consumption and update individual stocks
        current_group.calculate_consumption(bom_data)
        
        groups.append(current_group)
        group_counter += 1

    unassigned_ofs_final = [of for of in all_ofs if of.assigned_group_id is None]
    if unassigned_ofs_final:
        print("\nWarning: Some OFs remain unassigned after grouping:")
        for of in unassigned_ofs_final: print(f"  - {of}")
            
    return groups, all_ofs

def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    print("\n--- Starting Detailed Smoothing and Scheduling ---")

    print("[DEBUG] Stocks avant scheduling:")
    for of in all_ofs_with_groups:
        if of.assigned_group_id:
            print(f"  {of.id} ({of.product_id}): stock = {of.individual_product_stock}")

    def is_weekend(date_obj):
        return date_obj.weekday() >= 5

    all_scheduled_ofs = []

    for group in sorted(groups, key=lambda g: g.time_window_start):
        print(f"\nSmoothing Group {group.id} (Window: {group.time_window_start.strftime('%Y-%m-%d')} - {group.time_window_end.strftime('%Y-%m-%d')})")
        
        ofs_in_group_sorted = sorted(
            [of for of in all_ofs_with_groups if of.assigned_group_id == group.id],
            key=lambda x: (-x.bom_level, x.need_date)
        )

        for of_to_schedule in ofs_in_group_sorted:
            print(f"  Attempting to schedule OF {of_to_schedule.id} ({of_to_schedule.designation}), Need Date: {of_to_schedule.need_date.strftime('%Y-%m-%d')}")

            of_operations = operations_map.get(of_to_schedule.product_id, [])
            if not of_operations:
                of_operations = operations_map.get(of_to_schedule.product_type, [])

            if not of_operations:
                print(f"    Warning: No operations found for OF {of_to_schedule.id} (Product ID: {of_to_schedule.product_id}, Type: {of_to_schedule.product_type}). Skipping.")
                of_to_schedule.status = "FAILED_PLANNING_NO_OPS"
                all_scheduled_ofs.append(of_to_schedule)
                continue

            of_operations_sorted = sorted(of_operations, key=lambda op: op.sequence)
            
            current_of_scheduled_start_date = None
            current_of_scheduled_end_date = None
            possible_to_schedule_of = True
            last_op_end_datetime = None

            for op_def in of_operations_sorted:
                post_obj = posts_map.get(op_def.post_id)
                if post_obj:
                    post_obj.clear_schedule_for_of(of_to_schedule.id + "_" + op_def.operation_name)

            adv_retreat_delta = timedelta(weeks=params.get("advance_retreat_weeks", ADVANCE_RETREAT_WEEKS))
            earliest_start_date_boundary = of_to_schedule.need_date - adv_retreat_delta
            latest_start_date_boundary_for_first_op = of_to_schedule.need_date + adv_retreat_delta

            initial_search_start_dt = max(
                group.time_window_start,
                earliest_start_date_boundary 
            )
            if isinstance(initial_search_start_dt, date) and not isinstance(initial_search_start_dt, datetime):
                initial_search_start_dt = datetime.combine(initial_search_start_dt, time.min)

            op_schedule_details = []
            last_op_end_datetime = None

            for i, op_def in enumerate(of_operations_sorted):
                post_obj = posts_map.get(op_def.post_id)
                if not post_obj:
                    print(f"    Warning: Post {op_def.post_id} for operation {op_def.operation_name} of OF {of_to_schedule.id} not found.")
                    possible_to_schedule_of = False
                    break

                op_duration_hours = op_def.standard_time_hours
                
                current_op_search_start_dt = last_op_end_datetime if last_op_end_datetime else initial_search_start_dt
                current_op_search_start_dt = post_obj._get_next_working_datetime(current_op_search_start_dt)

                latest_boundary_date = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                if i == 0 and current_op_search_start_dt.date() > latest_boundary_date:
                    boundary_str = latest_start_date_boundary_for_first_op.strftime('%Y-%m-%d') if hasattr(latest_start_date_boundary_for_first_op, 'strftime') else str(latest_start_date_boundary_for_first_op)
                    print(f"    OF {of_to_schedule.id}, Op {op_def.operation_name}: Initial search start {current_op_search_start_dt.strftime('%Y-%m-%d %H:%M')} is beyond latest boundary {boundary_str}.")
                    possible_to_schedule_of = False
                    break

                op_start_dt, op_end_dt = post_obj.find_available_slot(
                    current_op_search_start_dt, 
                    op_duration_hours,
                    of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name
                )

                if op_start_dt and op_end_dt:
                    latest_boundary_date_here = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                    if i == 0 and op_start_dt.date() > latest_boundary_date_here:
                        boundary_str = latest_start_date_boundary_for_first_op.strftime('%Y-%m-%d') if hasattr(latest_start_date_boundary_for_first_op, 'strftime') else str(latest_start_date_boundary_for_first_op)
                        print(f"    OF {of_to_schedule.id}, Op {op_def.operation_name}: Found slot {op_start_dt.strftime('%Y-%m-%d %H:%M')} is beyond latest boundary {boundary_str}.")
                        possible_to_schedule_of = False
                        break 
                    
                    print(f"      Op {op_def.operation_name} on {post_obj.id} tentatively scheduled: {op_start_dt.strftime('%Y-%m-%d %H:%M')} - {op_end_dt.strftime('%Y-%m-%d %H:%M')}")
                    op_schedule_details.append({'op_def': op_def, 'post_obj': post_obj, 'start_dt': op_start_dt, 'end_dt': op_end_dt})
                    
                    if i == 0:
                        current_of_scheduled_start_date = op_start_dt
                    
                    last_op_end_datetime = op_end_dt
                    current_of_scheduled_end_date = op_end_dt
                else:
                    print(f"    Could not find slot for Op {op_def.operation_name} on {post_obj.id} for OF {of_to_schedule.id} (duration: {op_duration_hours}h) starting around {current_op_search_start_dt.strftime('%Y-%m-%d %H:%M')}.")
                    possible_to_schedule_of = False
                    break

            if possible_to_schedule_of and op_schedule_details:
                for detail in op_schedule_details:
                    detail['post_obj'].book_slot(detail['start_dt'], detail['end_dt'], of_to_schedule.id + "_" + detail['op_def'].operation_name)
                
                of_to_schedule.scheduled_start_date = current_of_scheduled_start_date
                of_to_schedule.scheduled_end_date = current_of_scheduled_end_date

                latest_boundary_date_final = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                earliest_boundary_date_final = earliest_start_date_boundary.date() if isinstance(earliest_start_date_boundary, datetime) else earliest_start_date_boundary
                if (earliest_boundary_date_final <= of_to_schedule.scheduled_start_date.date() <= latest_boundary_date_final):
                    of_to_schedule.status = "PLANNED"
                    print(f"    OF {of_to_schedule.id} PLANNED. Start: {of_to_schedule.scheduled_start_date.strftime('%Y-%m-%d %H:%M')}, End: {of_to_schedule.scheduled_end_date.strftime('%Y-%m-%d %H:%M')}")
                else:
                    of_to_schedule.status = "PLANNED_OUTSIDE_WINDOW"
                    print(f"    OF {of_to_schedule.id} PLANNED_OUTSIDE_WINDOW. Need: {of_to_schedule.need_date.strftime('%Y-%m-%d')}, Start: {of_to_schedule.scheduled_start_date.strftime('%Y-%m-%d %H:%M')}")
            
            else:
                of_to_schedule.status = "FAILED_PLANNING"
                print(f"    OF {of_to_schedule.id} FAILED_PLANNING (could not schedule all operations).")

            all_scheduled_ofs.append(of_to_schedule)

    final_of_map = {of.id: of for of in all_scheduled_ofs}
    updated_all_ofs = []
    for original_of in all_ofs_with_groups:
        if original_of.id in final_of_map:
            updated_all_ofs.append(final_of_map[original_of.id])
        else:
            updated_all_ofs.append(original_of)
            if original_of.assigned_group_id and original_of.status not in ["PLANNED", "FAILED_PLANNING", "FAILED_PLANNING_NO_OPS", "PLANNED_OUTSIDE_WINDOW"]:
                 print(f"Warning: OF {original_of.id} was in a group but not processed by smoothing loop. Status: {original_of.status}")

    return updated_all_ofs

def load_ofs_from_file(filepath):
    print(f"Loading OFs from {filepath}")
    ofs = []
    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            delimiter = detect_csv_delimiter(filepath, fallback='\t')
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            expected_input_cols = ["Part", "Description", "Order Code", "FG", "CAT US FS", "Qty", "Date"]
            if not reader.fieldnames:
                print(f"Warning: CSV file {filepath} appears to be empty or header is missing.")
                return []
            
            header_map = {col.strip().lower(): col.strip() for col in reader.fieldnames}
            
            mapped_expected_cols = {}
            missing_cols = []
            for col_name in expected_input_cols:
                mapped_col_name = header_map.get(col_name.lower())
                if mapped_expected_cols is not None and mapped_col_name:
                    mapped_expected_cols[col_name] = mapped_col_name
                else:
                    missing_cols.append(col_name)

            if missing_cols:
                raise ValueError(f"CSV file {filepath} is missing one or more required columns: {missing_cols}. Found headers: {reader.fieldnames}")

            for row_num, row in enumerate(reader, 1):
                try:
                    part_val = row[mapped_expected_cols["Part"]]
                    product_type_derived = ""
                    if part_val.startswith("PF"): product_type_derived = "PF"
                    elif part_val.startswith("SF"): product_type_derived = "SF"
                    elif part_val.startswith("PS"): product_type_derived = "PS"
                    else:
                        print(f"Warning: Row {row_num}: Could not determine product_type from Part '{part_val}'. Defaulting to 'UNKNOWN'.")
                        product_type_derived = "UNKNOWN"

                    cat_us_fs_raw = (row.get(mapped_expected_cols["CAT US FS"], "") or "").strip()
                    cat_us_fs_parts = cat_us_fs_raw.split()

                    cat_val = ""
                    us_val = "1"
                    fs_val = "1"

                    if len(cat_us_fs_parts) == 3:
                        cat_val = cat_us_fs_parts[0]
                        us_val = cat_us_fs_parts[1]
                        fs_val = cat_us_fs_parts[2]
                    elif len(cat_us_fs_parts) == 1:
                        cat_val = cat_us_fs_parts[0]
                    elif len(cat_us_fs_parts) > 0:
                        cat_val = cat_us_fs_parts[0]
                        print(f"Warning: Row {row_num}: CAT US FS column ('{cat_us_fs_raw}') has an unexpected number of parts ({len(cat_us_fs_parts)}). Using '{cat_val}' as CAT, defaulting US/FS to '1'.")
                    else:
                        print(f"Warning: Row {row_num}: CAT US FS column is empty. Defaulting CAT to empty, US/FS to '1'.")
                        cat_val = ""

                    try:
                        bom_level_derived = int(cat_val) if cat_val else 0
                    except ValueError:
                        print(f"Warning: Row {row_num}: Could not convert CAT value '{cat_val}' to int for bom_level. Defaulting to 0.")
                        bom_level_derived = 0
                        
                    of = ManufacturingOrder(
                        id=row[mapped_expected_cols["Order Code"]],
                        designation=row[mapped_expected_cols["Description"]],
                        product_id=part_val,
                        product_type=product_type_derived,
                        bom_level=bom_level_derived,
                        need_date_str=row[mapped_expected_cols["Date"]],
                        quantity=row[mapped_expected_cols["Qty"]],
                        fg=row[mapped_expected_cols["FG"]],
                        cat=cat_val,
                        us=us_val,
                        fs=fs_val
                    )
                    ofs.append(of)
                except KeyError as e:
                    print(f"Warning: Missing key {e} in row {row_num} of {filepath}. Row: {row}")
                except ValueError as e:
                    print(f"Warning: Value error processing row {row_num} of {filepath}: {e}. Row: {row}")
                except Exception as e:
                    print(f"Warning: Unexpected error processing row {row_num} of {filepath}: {e}. Row: {row}")
    except FileNotFoundError:
        print(f"Error: OFs file not found at {filepath}. Returning empty list.")
        return []
    except ValueError as e:
        print(f"Error loading OFs from {filepath}: {e}")
        return []
    except Exception as e:
        print(f"Error loading OFs from {filepath}: {e}. Returning empty list.")
        return []
    print(f"Loaded {len(ofs)} OFs.")
    return ofs

def load_bom_from_file(filepath):
    print(f"Loading BOM from {filepath}")
    bom_entries = []
    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            delimiter = detect_csv_delimiter(filepath, fallback=',')
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols = ["ParentProductID", "ChildProductID", "QuantityChildPerParent", "ChildBOMLevel"]
            if not reader.fieldnames or not all(col in reader.fieldnames for col in required_cols):
                available_cols = reader.fieldnames if reader.fieldnames else []
                raise ValueError(f"CSV file {filepath} is missing one or more required columns: {required_cols}. Found: {available_cols}")

            for row_num, row in enumerate(reader, 1):
                try:
                    entry = BOMEntry(
                        parent_product_id=row["ParentProductID"],
                        child_product_id=row["ChildProductID"],
                        quantity_child_per_parent=row["QuantityChildPerParent"],
                        child_bom_level=row["ChildBOMLevel"]
                    )
                    bom_entries.append(entry)
                except KeyError as e:
                    print(f"Warning: Missing key {e} in row {row_num} of {filepath}. Row: {row}")
                except ValueError as e:
                    print(f"Warning: Value error processing row {row_num} of {filepath}: {e}. Row: {row}")
                except Exception as e:
                    print(f"Warning: Unexpected error processing row {row_num} of {filepath}: {e}. Row: {row}")
    except FileNotFoundError:
        print(f"Error: BOM file not found at {filepath}. Returning empty list.")
        return []
    except Exception as e:
        print(f"Error loading BOM from {filepath}: {e}. Returning empty list.")
        return []
    print(f"Loaded {len(bom_entries)} BOM entries.")
    return bom_entries

def load_posts_and_operations_data(filepath_posts, filepath_post_unavailability, filepath_operations):
    print(f"Loading Posts, Unavailability & Operations from {filepath_posts}, {filepath_post_unavailability}, {filepath_operations}")
    posts_map = {}
    
    try:
        with open(filepath_posts, mode='r', encoding='utf-8-sig') as csvfile:
            delimiter = detect_csv_delimiter(filepath_posts, fallback=',')
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols_posts = ["PostID", "PostName", "DefaultCapacityHoursWeek"]
            if not reader.fieldnames or not all(col in reader.fieldnames for col in required_cols_posts):
                available_cols = reader.fieldnames if reader.fieldnames else []
                raise ValueError(f"Posts CSV {filepath_posts} missing required columns. Need: {required_cols_posts}, Found: {available_cols}")
            for row in reader:
                post = Post(id=row["PostID"], name=row["PostName"], default_capacity_hours_week=int(row["DefaultCapacityHoursWeek"]))
                posts_map[post.id] = post
    except FileNotFoundError:
        print(f"Warning: Posts file not found at {filepath_posts}.")
    except Exception as e:
        print(f"Error loading Posts from {filepath_posts}: {e}")
    
    try:
        with open(filepath_post_unavailability, mode='r', encoding='utf-8-sig') as csvfile:
            delimiter = detect_csv_delimiter(filepath_post_unavailability, fallback=',')
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols_unavail = ["PostID", "UnavailableStartDate", "UnavailableEndDate"]
            if not all(col in reader.fieldnames for col in required_cols_unavail):
                raise ValueError(f"Post Unavailability CSV {filepath_post_unavailability} missing required columns. Need: {required_cols_unavail}, Found: {reader.fieldnames}")
            for row in reader:
                post_id = row["PostID"]
                if post_id in posts_map:
                    posts_map[post_id].add_unavailable_period(row["UnavailableStartDate"], row["UnavailableEndDate"])
                else:
                    print(f"Warning: PostID {post_id} from unavailability file not found in loaded posts.")
    except FileNotFoundError:
        print(f"Warning: Post unavailability file not found at {filepath_post_unavailability}.")
    except Exception as e:
        print(f"Error loading Post Unavailability from {filepath_post_unavailability}: {e}")

    operations_map = defaultdict(list)
    try:
        with open(filepath_operations, mode='r', encoding='utf-8-sig') as csvfile:
            delimiter = detect_csv_delimiter(filepath_operations, fallback=',')
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols_ops = ["ProductID", "OperationName", "PostID", "StandardTimeHours", "Sequence", "Priority"]
            if not all(col in reader.fieldnames for col in required_cols_ops):
                raise ValueError(f"Operations CSV {filepath_operations} missing required columns. Need: {required_cols_ops}, Found: {reader.fieldnames}")

            for row in reader:
                key = row.get('ProductID') if row.get('ProductID') else row.get('ProductType', 'UNKNOWN_OP_KEY')
                if key == 'UNKNOWN_OP_KEY':
                    print(f"Skipping operation due to missing ProductID/ProductType: {row}")
                    continue

                op = Operation(
                    product_key=key,
                    operation_name=row['OperationName'],
                    post_id=row['PostID'],
                    standard_time_hours=row['StandardTimeHours'],
                    sequence=int(row['Sequence']),
                    priority=int(row.get('Priority', 1))
                )
                operations_map[key].append(op)
    except FileNotFoundError:
        print(f"Warning: Operations file not found at {filepath_operations}.")
    except Exception as e:
        print(f"Error loading Operations from {filepath_operations}: {e}")

    print(f"Loaded {len(posts_map)} posts and {sum(len(ops) for ops in operations_map.values())} operation rules.")
    return posts_map, operations_map

def write_grouped_needs_to_file(filepath, grouped_list_data, all_ofs_scheduled):
    print(f"\nWriting grouped needs to {filepath}")
    
    output_header = [
        "Part", "Description", "Order Code", "FG", "CAT", "US", "FS", "Qty",
        "X3 Date", "GRP_FLG", "Start Date", "Delay", "Stock_Produit"
    ]

    with open(filepath, "w", newline='', encoding='utf-8') as f:
        import csv
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(output_header)

        processed_of_ids_in_groups = set()

        def extract_group_number(group):
            try:
                return int(group.id.replace("GRP", ""))
            except Exception:
                return 0

        # -------- GROUPES --------
        for group in sorted(grouped_list_data, key=extract_group_number):
            f.write(f"\n# Group ID: {group.id}\n")
            f.write(f"#   Produit PS Principal: {group.ps_product_id}\n")
            f.write(
                f"#   Fenêtre Temporelle: {group.time_window_start.strftime('%Y-%m-%d')} "
                f"à {group.time_window_end.strftime('%Y-%m-%d')}\n"
            )

            if hasattr(group, "individual_product_stocks") and group.ps_product_id in group.individual_product_stocks:
                f.write(f"#   Stock PS Calculé: {group.individual_product_stocks[group.ps_product_id]:.2f}\n")
            else:
                f.write("#   Stock PS: Non calculé\n")

            ofs_in_group = [of for of in all_ofs_scheduled if of.assigned_group_id == group.id]

            for of_obj in sorted(ofs_in_group, key=lambda x: (-x.bom_level, x.need_date)):
                # description courte
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
                grp_flg = of_obj.assigned_group_id.replace("GRP", "") if of_obj.assigned_group_id else ""
                start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""

                delay_val = ""
                if of_obj.scheduled_start_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))

                # ⬇️ on prend EXACTEMENT ce que le calcul a mis
                stock_val = getattr(of_obj, "individual_product_stock", None)
                if stock_val is None:
                    stock_val = getattr(of_obj, "remaining_stock", 0.0)
                if stock_val is None:
                    stock_val = 0.0

                # on n'arrondit plus
                if isinstance(stock_val, float):
                    # tu peux choisir la précision que tu veux, ou juste str()
                    stock_display = str(stock_val)
                else:
                    stock_display = str(stock_val)


                print(
                    f"[WRITE][{group.id}] OF {of_obj.id} ({of_obj.product_id}) "
                    f"indiv={getattr(of_obj, 'individual_product_stock', None)} "
                    f"remaining_attr={getattr(of_obj, 'remaining_stock', None)} "
                    f"-> écrit={stock_display}"
                )

                qty_display = getattr(of_obj, "source_qty", None)
                if not qty_display:  # si pas trouvé ou vide
                    qty_display = int(of_obj.quantity)  # fallback comme avant
                writer.writerow([
                    of_obj.product_id,
                    processed_description,
                    processed_order_code,
                    of_obj.fg,
                    of_obj.cat,
                    of_obj.us,
                    of_obj.fs,
                    qty_display,
                    of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                    grp_flg,
                    start_date_str,
                    delay_val,
                    stock_display
                ])

                processed_of_ids_in_groups.add(of_obj.id)

        # -------- OF NON AFFECTÉS --------
        f.write("\n# OFs Non Affectés:\n")
        unassigned = [of for of in all_ofs_scheduled if of.id not in processed_of_ids_in_groups]

        for of_obj in sorted(unassigned, key=lambda x: x.id):
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
            grp_flg = of_obj.assigned_group_id.replace("GRP", "") if of_obj.assigned_group_id else ""
            start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""

            delay_val = ""
            if of_obj.scheduled_start_date and of_obj.need_date:
                delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                delay_val = str(max(0, delay_days))

            stock_val = getattr(of_obj, "individual_product_stock", None)
            if stock_val is None:
                stock_val = getattr(of_obj, "remaining_stock", 0.0)
            if stock_val is None:
                stock_val = 0.0

            try:
                stock_display = f"{float(stock_val):.2f}"
            except (TypeError, ValueError):
                stock_display = str(stock_val)

            print(
                f"[WRITE][UNASSIGNED] OF {of_obj.id} ({of_obj.product_id}) "
                f"indiv={getattr(of_obj, 'individual_product_stock', None)} "
                f"remaining_attr={getattr(of_obj, 'remaining_stock', None)} "
                f"-> écrit={stock_display}"
            )

            writer.writerow([
                of_obj.product_id,
                processed_description,
                processed_order_code,
                of_obj.fg,
                of_obj.cat,
                of_obj.us,
                of_obj.fs,
                int(of_obj.quantity),
                of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                grp_flg,
                start_date_str,
                delay_val,
                stock_display
            ])

    print(f"Output written to {filepath} with individual product stocks.")


def load_compact_input_file(filepath):
    """
    Charge un fichier d'entrée compact où les OFs et la nomenclature sont dans un seul fichier tabulé.
    """
    ofs_list = []
    bom_list = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if parts[0].upper() == 'OFS':
                try:
                    _, of_id, designation, product_id, fg, cat, us, fs, qty, need_date = parts[:10]
                    if product_id.startswith('PF'):
                        product_type = 'PF'
                    elif product_id.startswith('SF'):
                        product_type = 'SF'
                    elif product_id.startswith('PS'):
                        product_type = 'PS'
                    else:
                        product_type = 'UNKNOWN'
                    try:
                        bom_level = int(cat) if cat else 0
                    except ValueError:
                        bom_level = 0
                    ofs_list.append(ManufacturingOrder(
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
                        fs=fs
                    ))
                except Exception as e:
                    print(f"Erreur parsing OFS: {e} | Ligne: {line}")
            elif parts[0].upper() == 'BOM':
                try:
                    _, parent, child, qty_per_parent, child_level = parts[:5]
                    bom_list.append(BOMEntry(
                        parent_product_id=parent,
                        child_product_id=child,
                        quantity_child_per_parent=qty_per_parent,
                        child_bom_level=child_level
                    ))
                except Exception as e:
                    print(f"Erreur parsing BOM: {e} | Ligne: {line}")
    return ofs_list, bom_list

# --- Main Execution ---
if __name__ == "__main__":
    compact_file = "input_compact.txt"
    ofs_file = "test_besoins.csv"
    bom_file = "test_nomenclature.csv"
    posts_file = "test_posts.csv"
    post_unavailability_file = "post_unavailability.csv"
    operations_file = "test_operations.csv"
    output_file = "test_besoins_groupes_output.txt"

    if os.path.exists(compact_file):
        print(f"Mode compact détecté : chargement depuis {compact_file}")
        all_ofs, bom_data = load_compact_input_file(compact_file)
    else:
        print("Mode classique : chargement des fichiers CSV classiques.")
        all_ofs = load_ofs_from_file(ofs_file)
        bom_data = load_bom_from_file(bom_file)

    posts_map, operations_map = load_posts_and_operations_data(posts_file, post_unavailability_file, operations_file)

    params = {
        "advance_retreat_weeks": ADVANCE_RETREAT_WEEKS
    }

    groups, all_ofs_with_groups = run_grouping_algorithm(all_ofs, bom_data, HORIZON_H_WEEKS)

    all_ofs_scheduled = smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params)

    write_grouped_needs_to_file(output_file, groups, all_ofs_scheduled)

    print(f"\nTraitement terminé. Résultat écrit dans {output_file}.")