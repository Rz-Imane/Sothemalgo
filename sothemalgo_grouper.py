from datetime import datetime, timedelta, time, date # Ensure date is imported
from collections import defaultdict
import calendar
import csv # Added for CSV reading

# --- Configuration & Parameters ---
HORIZON_H_MONTHS = 1 # Example: 1 month horizon for F(i) - used for window duration calculation via weeks
HORIZON_H_WEEKS = 4 # Defines the duration of the time window F(i), e.g., 4 weeks for 1 month
POST_DEFAULT_CAPACITY_HOURS_WEEK = 35
ADVANCE_RETREAT_WEEKS = 3

# --- Data Structures ---
class ManufacturingOrder:
    def __init__(self, id, designation, product_id, product_type, bom_level, need_date_str, quantity, fg, cat, us, fs, unit="U", status="UNASSIGNED"):
        self.id = id
        self.designation = designation
        self.product_id = product_id
        self.product_type = product_type  # "PS", "SF", "PF"
        self.bom_level = int(bom_level) # Higher number = more upstream
        try:
            self.need_date = datetime.strptime(need_date_str, "%Y-%m-%d")
        except ValueError:
            try:
                self.need_date = datetime.strptime(need_date_str, "%d/%m/%Y")
            except ValueError:
                try:
                    self.need_date = datetime.strptime(need_date_str, "%d/%m/%y")
                except ValueError:
                    raise ValueError(f"Date format for {need_date_str} not recognized. Use YYYY-MM-DD, DD/MM/YYYY, or DD/MM/YY.")
        self.quantity = float(quantity)
        self.unit = unit
        self.assigned_group_id = None
        self.status = "UNASSIGNED"
        self.scheduled_start_date = None
        self.scheduled_end_date = None
        self.fg = fg
        self.cat = cat
        self.us = us
        self.fs = fs

    def __repr__(self):
        return (f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.product_id}', type='{self.product_type}', "
                f"level={self.bom_level}, need={self.need_date.strftime('%Y-%m-%d')}, qty={self.quantity}, "
                f"fg='{self.fg}', cat='{self.cat}', " # Added fg, cat
                f"group={self.assigned_group_id}, status='{self.status}')")

class BOMEntry:
    def __init__(self, parent_product_id, child_product_id, quantity_child_per_parent, child_bom_level):
        self.parent_product_id = parent_product_id
        self.child_product_id = child_product_id
        self.quantity_child_per_parent = float(quantity_child_per_parent)
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
        self.ofs = [] # List of ManufacturingOrder objects
        self.current_ps_stock_available = 0
        self.component_stocks = {}  # Nouveau : stock par composant (PS, SF1, SF2, etc.)
        self.add_of(initial_ps_of, ps_quantity_change=initial_ps_of.quantity) # Add initial OF

    def add_of(self, of_to_add, ps_quantity_change=0):
        self.ofs.append(of_to_add)
        self.current_ps_stock_available += ps_quantity_change
        # Mise à jour du stock par composant
        if of_to_add.product_id not in self.component_stocks:
            self.component_stocks[of_to_add.product_id] = 0
        self.component_stocks[of_to_add.product_id] += ps_quantity_change
        of_to_add.assigned_group_id = self.id
        of_to_add.status = "ASSIGNED" # Mark as assigned to this group

    def __repr__(self):
        return (f"Group(id={self.id}, PS_prod='{self.ps_product_id}', "
                f"window=[{self.time_window_start.strftime('%Y-%m-%d')}-{self.time_window_end.strftime('%Y-%m-%d')}], "
                f"PS_stock={self.current_ps_stock_available}, num_ofs={len(self.ofs)})")

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
        ws = datetime.combine(date.min, self.work_start_time) # Changed from datetime.date.min
        we = datetime.combine(date.min, self.work_end_time) # Changed from datetime.date.min
        ls = datetime.combine(date.min, self.lunch_start_time) # Changed from datetime.date.min
        le = datetime.combine(date.min, self.lunch_end_time) # Changed from datetime.date.min

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
        
        self.unavailable_periods = [] # List of (start_datetime, end_datetime) tuples, kept sorted
        self.scheduled_slots = [] # List of (start_datetime, end_datetime, of_id) tuples, kept sorted

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
        # Check if a specific datetime is a working moment (correct day, time, not lunch, not unavailable)
        if dt_obj.weekday() >= 5: # Saturday or Sunday
            return False
        
        current_time = dt_obj.time()
        if not (self.work_start_time <= current_time < self.work_end_time):
            return False
        
        if self.lunch_start_time <= current_time < self.lunch_end_time:
            return False
        
        for un_start, un_end in self.unavailable_periods:
            if un_start <= dt_obj <= un_end: # Inclusive check for unavailability
                return False
        return True

    def _get_next_working_datetime(self, current_dt_orig):
        current_dt = current_dt_orig
        # Limit search to avoid excessively long loops if configuration is problematic
        max_iterations = 10000 # Approx 1 week of minutes + some jumps
        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            # 1. Align to start of minute
            current_dt = current_dt.replace(second=0, microsecond=0)

            # 2. Handle date-level skips (weekend, unavailability)
            while True:
                date_changed = False
                if current_dt.weekday() >= 5: # Skip weekends
                    current_dt = (current_dt + timedelta(days=1)).replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                    date_changed = True
                    continue # Re-check new day

                is_unavailable_day = False
                for un_start, un_end in self.unavailable_periods:
                    # If current_dt is within a full-day or multi-day unavailability period
                    if un_start.date() <= current_dt.date() <= un_end.date():
                        # If current_dt is before or within the period, jump to its end + 1 minute, then align
                        if current_dt < un_end:
                             current_dt = (un_end + timedelta(minutes=1)) # Move past the unavailability
                             current_dt = current_dt.replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                             date_changed = True
                             is_unavailable_day = True # Mark to re-evaluate the new current_dt
                             break
                if is_unavailable_day:
                    continue # Re-check new day/time after jumping past unavailability

                break # Current date is a weekday and not in a full unavailability block

            # 3. Handle time-level adjustments within a working day
            current_time = current_dt.time()

            if current_time >= self.work_end_time: # After work hours
                current_dt = (current_dt + timedelta(days=1)).replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                continue # Re-evaluate new day

            if current_time < self.work_start_time: # Before work hours
                current_dt = current_dt.replace(hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                # Fall through to check lunch / specific unavailability

            current_time = current_dt.time() # Re-fetch time after potential adjustment

            if self.lunch_start_time <= current_time < self.lunch_end_time: # During lunch
                current_dt = current_dt.replace(hour=self.lunch_end_time.hour, minute=self.lunch_end_time.minute)
                # If lunch end is work end or later, this will be caught by "After work hours" in next iteration
                continue

            # Check again for specific unavailability periods that might affect the current time
            is_currently_unavailable = False
            for un_start, un_end in self.unavailable_periods:
                 if un_start <= current_dt < un_end : # current_dt is within an unavailability slot
                      current_dt = un_end # Jump to the end of this specific slot
                      is_currently_unavailable = True
                      break
            if is_currently_unavailable:
                 continue # Re-evaluate current_dt from the top of the time-level adjustments

            # If all checks pass, this is a working moment
            if self._is_working_moment(current_dt):
                return current_dt
            
            # Fallback: if stuck, advance by one minute and retry (should be rare)
            # This might happen if _is_working_moment has subtle conditions not caught by jumps
            current_dt += timedelta(minutes=1)

        print(f"Warning: Post {self.id} _get_next_working_datetime exceeded max iterations from {current_dt_orig}. Returning original.")
        return current_dt_orig # Fallback, indicates a problem

    def calculate_end_datetime(self, start_dt_param, duration_hours):
        if duration_hours <= 0:
            return start_dt_param

        # Ensure the operation starts at a valid working moment
        actual_start_dt = self._get_next_working_datetime(start_dt_param)
        
        # If the next working datetime is significantly different from requested, it implies the slot is not good.
        # The caller (find_available_slot) should handle this by trying a new start_dt_param.
        # Here, we proceed with actual_start_dt.
        
        current_dt = actual_start_dt
        remaining_seconds = duration_hours * 3600
        
        max_calc_iterations = 20000 # Safety break for calculation
        calc_iter = 0

        while remaining_seconds > 0 and calc_iter < max_calc_iterations:
            calc_iter += 1
            if not self._is_working_moment(current_dt):
                current_dt = self._get_next_working_datetime(current_dt)
                # If _get_next_working_datetime returns the same time, we are stuck
                if current_dt == self._get_next_working_datetime(current_dt + timedelta(microseconds=1)) and self._is_working_moment(current_dt) == False :
                    print(f"Error: Post {self.id} calculate_end_datetime stuck finding next working moment from {current_dt}.")
                    return datetime.max # Indicate failure
                continue

            # Time available in the current continuous working block (until lunch, end of day, or next unavailability)
            # This is a simplification: we check minute by minute.
            # A more optimized way would calculate the length of the current continuous slot.
            
            next_minute_dt = current_dt + timedelta(minutes=1)
            
            if self._is_working_moment(current_dt): # current_dt is a working minute
                seconds_this_minute = 60
                can_consume_seconds = min(remaining_seconds, seconds_this_minute)
                remaining_seconds -= can_consume_seconds
                current_dt = next_minute_dt # Advance by one minute
            else: # Should not happen if _get_next_working_datetime worked
                current_dt = self._get_next_working_datetime(current_dt)


        if remaining_seconds > 0:
            print(f"Warning: Post {self.id} calculate_end_datetime could not schedule full duration. Remaining: {remaining_seconds/3600} hrs.")
            return datetime.max # Indicate failure to schedule full duration

        # The end_dt is the beginning of the minute *after* the work is done.
        # So, if an op ends at 08:59:59, it means it finished within the minute 08:59.
        # The 'current_dt' is now at the start of the next minute.
        return current_dt 

    def find_available_slot(self, search_start_dt_param, duration_hours, of_id_to_ignore=None):
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        
        # Safety: limit how far in the future we search
        max_search_datetime = search_start_dt_param + timedelta(days=180) # e.g., 6 months

        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)

            if potential_end_dt == datetime.max: # Cannot find a valid end time from this start
                # Advance search: try next day to avoid getting stuck on a bad start time
                current_try_start_dt = (current_try_start_dt + timedelta(days=1)).replace(
                    hour=self.work_start_time.hour, minute=self.work_start_time.minute)
                current_try_start_dt = self._get_next_working_datetime(current_try_start_dt)
                continue

            is_overlap = False
            for booked_start, booked_end, booked_of_id in self.scheduled_slots:
                if of_id_to_ignore and booked_of_id == of_id_to_ignore:
                    continue
                # Overlap if (StartA < EndB) and (EndA > StartB)
                if current_try_start_dt < booked_end and potential_end_dt > booked_start:
                    is_overlap = True
                    # Advance current_try_start_dt to the end of the conflicting slot
                    current_try_start_dt = self._get_next_working_datetime(booked_end)
                    break 
            
            if not is_overlap:
                return current_try_start_dt, potential_end_dt # Found a slot

            # If loop continues, current_try_start_dt has been advanced by _get_next_working_datetime(booked_end)
            # or by advancing to the next day if potential_end_dt was datetime.max

        print(f"Warning: Slot search for post {self.id} exceeded search limit from {search_start_dt_param} for {duration_hours}hr task.")
        return None, None
    
    def book_slot(self, start_dt, end_dt, of_id):
        # Remove any existing slots for this of_id first to handle re-booking
        self.clear_schedule_for_of(of_id)
        
        self.scheduled_slots.append((start_dt, end_dt, of_id))
        self.scheduled_slots.sort()

    def clear_schedule_for_of(self, of_id):
        self.scheduled_slots = [(s, e, o) for s, e, o in self.scheduled_slots if o != of_id]

    def __repr__(self):
        return f"Post(id={self.id}, name='{self.name}', daily_hours={self.daily_capacity_hours:.2f}, unavailable_periods={len(self.unavailable_periods)}, scheduled_slots={len(self.scheduled_slots)})"

class Operation:
    def __init__(self, product_key, operation_name, post_id, standard_time_hours, sequence, priority):
        self.product_key = product_key # Changed from of_id
        self.operation_name = operation_name
        self.post_id = post_id
        self.standard_time_hours = standard_time_hours
        self.sequence = sequence
        self.priority = priority

# --- Helper Functions ---
def get_monday_of_week(d):
    return d - timedelta(days=d.weekday())

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

# --- Step 1: Tri et initialisation ---
def sort_ofs_for_grouping(of_list):
    return sorted(of_list, key=lambda of: (of.designation, -of.bom_level, of.need_date))

# --- Main Grouping Algorithm ---
def run_grouping_algorithm(all_ofs, bom_data, horizon_H_weeks_param):
    group_counter = 1
    groups = []
    
    # Nouvelle approche conforme aux spécifications : partir des besoins clients mais utiliser la date PS pour la fenêtre
    while True:
        # Prioriser les OFs PF/SF non assignés (par niveau BOM décroissant puis date)
        unassigned_client_ofs = sorted(
            [of for of in all_ofs if of.product_type in ["PF", "SF"] and of.assigned_group_id is None],
            key=lambda of: (-of.bom_level, of.need_date, of.designation)
        )

        if not unassigned_client_ofs: break

        base_client_of = unassigned_client_ofs[0]
        
        # Calculer tous les composants nécessaires pour ce PF/SF
        needed_components = {}
        for bom_entry in bom_data:
            qty_needed = find_qty_of_component_in_product(base_client_of.product_id, bom_entry.child_product_id, bom_data)
            if qty_needed > 0:
                needed_components[bom_entry.child_product_id] = qty_needed * base_client_of.quantity
        
        # Identifier le PS principal (Premix) en privilégiant celui avec la date la plus tôt
        # et en respectant la hiérarchie de la nomenclature
        main_premix = None
        earliest_premix_date = None
        premix_date = None
        
        # D'abord, essayer de trouver le PS qui a la date la plus proche du besoin client
        best_premix_candidate = None
        best_date_diff = float('inf')
        
        for comp_id, qty in needed_components.items():
            # Chercher un OF PS correspondant pour obtenir sa date
            ps_ofs = [of for of in all_ofs if of.product_id == comp_id and of.product_type == "PS" and of.assigned_group_id is None]
            if ps_ofs:
                # Trouver le PS avec la date la plus proche de la date de besoin du client
                closest_ps = min(ps_ofs, key=lambda x: abs((x.need_date - base_client_of.need_date).days))
                date_diff = abs((closest_ps.need_date - base_client_of.need_date).days)
                
                if date_diff < best_date_diff:
                    best_date_diff = date_diff
                    best_premix_candidate = comp_id
                    premix_date = closest_ps.need_date
        
        main_premix = best_premix_candidate
        
        if not main_premix or not premix_date:
            # Fallback : utiliser la date du client et créer un PS fictif
            main_premix = f"PS_GROUP_{group_counter}"
            premix_date = base_client_of.need_date
        
        # IMPORTANT : Créer la fenêtre basée sur la DATE DU PREMIX (PS), pas du client
        window_start_date_monday = get_monday_of_week(premix_date)
        window_duration_td = timedelta(weeks=horizon_H_weeks_param)
        window_end_date = window_start_date_monday + window_duration_td - timedelta(days=1)
        
        # Créer le groupe avec le PF/SF comme base mais fenêtre basée sur PS
        current_group = Group(f"GRP{group_counter}", main_premix, base_client_of, window_start_date_monday, window_end_date)
        
        # Initialiser les stocks de composants nécessaires
        for comp_id, qty_needed in needed_components.items():
            current_group.component_stocks[comp_id] = -qty_needed  # Négatif car c'est un besoin
        
        print(f"Created {current_group} with client OF {base_client_of.id}, premix window based on {main_premix} date {premix_date.strftime('%Y-%m-%d')}")

        # Ajouter les OFs PS (Premix) disponibles dans la fenêtre pour satisfaire les besoins
        available_ps_ofs = [
            of for of in all_ofs 
            if of.product_type == "PS" and 
               of.assigned_group_id is None and
               window_start_date_monday <= of.need_date <= window_end_date
        ]
        
        for ps_of in sorted(available_ps_ofs, key=lambda o: o.need_date):
            if ps_of.product_id in needed_components:
                # Ce PS est nécessaire pour le groupe
                current_group.add_of(ps_of, ps_quantity_change=ps_of.quantity)
                current_group.component_stocks[ps_of.product_id] += ps_of.quantity
                print(f"  Added Premix OF {ps_of.id} ({ps_of.product_id}) to {current_group.id}. Stock {ps_of.product_id}: {current_group.component_stocks[ps_of.product_id]}")

        # Ajouter d'autres OFs PF/SF compatibles dans la même fenêtre
        # IMPORTANT: D'abord identifier tous les OFs de la même famille puis les ajouter tous
        other_client_ofs = [
            of for of in all_ofs 
            if of.product_type in ["PF", "SF"] and 
               of.assigned_group_id is None and
               of.id != base_client_of.id and
               window_start_date_monday <= of.need_date <= window_end_date
        ]
        
        # Stratégie révisée: grouper par famille de produits (partage les mêmes composants PS)
        for client_of in sorted(other_client_ofs, key=lambda o: o.need_date):
            # Calculer les besoins pour cet OF
            client_needed_components = {}
            for bom_entry in bom_data:
                qty_needed = find_qty_of_component_in_product(client_of.product_id, bom_entry.child_product_id, bom_data)
                if qty_needed > 0:
                    client_needed_components[bom_entry.child_product_id] = qty_needed * client_of.quantity
            
            # Vérifier si cet OF appartient à la même famille (utilise les mêmes PS)
            same_family = False
            for comp_id in client_needed_components.keys():
                if comp_id in needed_components:
                    same_family = True
                    break
            
            if same_family:
                # Ajouter l'OF à la même famille (il pourrait contribuer au stock)
                current_group.add_of(client_of, ps_quantity_change=0)
                
                # Si c'est un SF, il contribue au stock
                if client_of.product_type == "SF":
                    current_group.component_stocks[client_of.product_id] += client_of.quantity
                
                # Décrémenter les besoins en composants
                for comp_id, qty_needed in client_needed_components.items():
                    if comp_id not in current_group.component_stocks:
                        current_group.component_stocks[comp_id] = 0
                    current_group.component_stocks[comp_id] -= qty_needed
                    
                print(f"  Added family OF {client_of.id} ({client_of.product_type}) to {current_group.id}. Updated component stocks.")
            else:
                print(f"  Skipped client OF {client_of.id} - insufficient component stocks in {current_group.id}")
        
        groups.append(current_group)
        group_counter += 1

    unassigned_ofs_final = [of for of in all_ofs if of.assigned_group_id is None]
    if unassigned_ofs_final:
        print("\nWarning: Some OFs remain unassigned after grouping:")
        for of in unassigned_ofs_final: print(f"  - {of}")
            
    return groups, all_ofs

# --- Placeholder for Detailed Smoothing and Scheduling ---
def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    print("\\n--- Starting Detailed Smoothing and Scheduling ---")
    
    # Convert posts list to a dictionary for easier lookup
    # posts_map = {post.id: post for post in posts}

    # Helper to check if a date is a weekend
    def is_weekend(date_obj):
        return date_obj.weekday() >= 5 # 5 for Saturday, 6 for Sunday

    all_scheduled_ofs = []

    for group in sorted(groups, key=lambda g: g.time_window_start):
        print(f"\\nSmoothing Group {group.id} (Window: {group.time_window_start.strftime('%Y-%m-%d')} - {group.time_window_end.strftime('%Y-%m-%d')})")
        
        # Sort OFs within the group: PS first, then by original need date.
        # This helps ensure PS are planned before their consuming PFs/SFs within the group.
        ofs_in_group_sorted = sorted(
            [of for of in all_ofs_with_groups if of.assigned_group_id == group.id],
            key=lambda x: (-x.bom_level, x.need_date)
        )

        # Keep track of scheduled operations to manage post capacity
        # weekly_post_load = defaultdict(lambda: defaultdict(float)) # {week_start_monday: {post_id: hours_loaded}}
        
        # For simplicity, this example won't implement full capacity tracking across all groups simultaneously
        # but will focus on one OF at a time. A more robust system would need global capacity view.

        for of_to_schedule in ofs_in_group_sorted:
            print(f"  Attempting to schedule OF {of_to_schedule.id} ({of_to_schedule.designation}), Need Date: {of_to_schedule.need_date.strftime('%Y-%m-%d')}")

            # Try to get operations for the product_id first, then by product_type as a fallback
            of_operations = operations_map.get(of_to_schedule.product_id, [])
            if not of_operations:
                of_operations = operations_map.get(of_to_schedule.product_type, [])

            if not of_operations:
                print(f"    Warning: No operations found for OF {of_to_schedule.id} (Product ID: {of_to_schedule.product_id}, Type: {of_to_schedule.product_type}). Skipping.")
                of_to_schedule.status = "FAILED_PLANNING_NO_OPS"
                all_scheduled_ofs.append(of_to_schedule)
                continue

            # Sort operations by sequence
            of_operations_sorted = sorted(of_operations, key=lambda op: op.sequence)
            
            current_of_scheduled_start_date = None
            current_of_scheduled_end_date = None # This will be the end of the *last* operation
            possible_to_schedule_of = True # Assume true, set to false on failure
            
            # R3: Continuité des opérations - La date de fin d'une opération devient la date de début de la suivante
            last_op_end_datetime = None

            # Clear any previous bookings for this OF (in case of re-scheduling attempts not yet implemented)
            for op_def in of_operations_sorted:
                post_obj = posts_map.get(op_def.post_id)
                if post_obj:
                    post_obj.clear_schedule_for_of(of_to_schedule.id + "_" + op_def.operation_name) # Unique ID for booking

            # Étape 5 Lissage - Optimisation (R4 : Optimisation)
            # Try to schedule within a window: need_date - ADVANCE_RETREAT_WEEKS to need_date + ADVANCE_RETREAT_WEEKS
            
            # Define the scheduling window based on need date and advance/retreat parameters
            adv_retreat_delta = timedelta(weeks=params.get("advance_retreat_weeks", ADVANCE_RETREAT_WEEKS))
            earliest_start_date_boundary = of_to_schedule.need_date - adv_retreat_delta
            latest_start_date_boundary_for_first_op = of_to_schedule.need_date + adv_retreat_delta # This is for the *start* of the first op

            # Initial search start for the first operation:
            # Try to start as early as possible within the group window or the OF's own earliest boundary
            initial_search_start_dt = max(
                group.time_window_start, # Cannot start before group window
                earliest_start_date_boundary 
            )
            # Ensure it's a datetime object for Post methods
            if isinstance(initial_search_start_dt, date) and not isinstance(initial_search_start_dt, datetime):
                initial_search_start_dt = datetime.combine(initial_search_start_dt, time.min)


            op_schedule_details = [] # To store (op, start_dt, end_dt) for booking if all ops succeed

            for i, op_def in enumerate(of_operations_sorted):
                post_obj = posts_map.get(op_def.post_id)
                if not post_obj:
                    print(f"    Warning: Post {op_def.post_id} for operation {op_def.operation_name} of OF {of_to_schedule.id} not found.")
                    possible_to_schedule_of = False
                    break # Cannot schedule this OF

                op_duration_hours = op_def.standard_time_hours
                
                # Determine search start for this operation
                # For the first operation, it's initial_search_start_dt
                # For subsequent operations, it's the end time of the previous operation (R3)
                current_op_search_start_dt = last_op_end_datetime if last_op_end_datetime else initial_search_start_dt

                # Ensure search starts at a working time
                current_op_search_start_dt = post_obj._get_next_working_datetime(current_op_search_start_dt)

                # R1: Capacité - find_available_slot handles this
                # R2: Priorité des postes - TODO: Implement if multiple posts can do an operation
                
                # For the first operation, its start must also be within latest_start_date_boundary_for_first_op
                latest_boundary_date = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                if i == 0 and current_op_search_start_dt.date() > latest_boundary_date: # MODIFIED
                    boundary_str = latest_start_date_boundary_for_first_op.strftime('%Y-%m-%d') if hasattr(latest_start_date_boundary_for_first_op, 'strftime') else str(latest_start_date_boundary_for_first_op)
                    print(f"    OF {of_to_schedule.id}, Op {op_def.operation_name}: Initial search start {current_op_search_start_dt.strftime('%Y-%m-%d %H:%M')} is beyond latest boundary {boundary_str}.")
                    possible_to_schedule_of = False
                    break

                op_start_dt, op_end_dt = post_obj.find_available_slot(
                    current_op_search_start_dt, 
                    op_duration_hours,
                    of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name # Unique ID for booking
                )

                if op_start_dt and op_end_dt:
                    # Check if this operation (specifically the first one) respects the latest start boundary
                    latest_boundary_date_here = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                    if i == 0 and op_start_dt.date() > latest_boundary_date_here: # MODIFIED
                        boundary_str = latest_start_date_boundary_for_first_op.strftime('%Y-%m-%d') if hasattr(latest_start_date_boundary_for_first_op, 'strftime') else str(latest_start_date_boundary_for_first_op)
                        print(f"    OF {of_to_schedule.id}, Op {op_def.operation_name}: Found slot {op_start_dt.strftime('%Y-%m-%d %H:%M')} is beyond latest boundary {boundary_str}.")
                        possible_to_schedule_of = False
                        # No need to clear bookings here as they haven't been made yet
                        break 
                    
                    print(f"      Op {op_def.operation_name} on {post_obj.id} tentatively scheduled: {op_start_dt.strftime('%Y-%m-%d %H:%M')} - {op_end_dt.strftime('%Y-%m-%d %H:%M')}")
                    op_schedule_details.append({'op_def': op_def, 'post_obj': post_obj, 'start_dt': op_start_dt, 'end_dt': op_end_dt})
                    
                    if i == 0:
                        current_of_scheduled_start_date = op_start_dt # Start of the first operation
                    
                    last_op_end_datetime = op_end_dt # For the next operation in sequence
                    current_of_scheduled_end_date = op_end_dt # End of the *current* last successfully scheduled op
                else:
                    print(f"    Could not find slot for Op {op_def.operation_name} on {post_obj.id} for OF {of_to_schedule.id} (duration: {op_duration_hours}h) starting around {current_op_search_start_dt.strftime('%Y-%m-%d %H:%M')}.")
                    possible_to_schedule_of = False
                    break # Stop trying to schedule remaining ops for this OF

            if possible_to_schedule_of and op_schedule_details:
                # All operations for this OF have found tentative slots. Now book them.
                for detail in op_schedule_details:
                    detail['post_obj'].book_slot(detail['start_dt'], detail['end_dt'], of_to_schedule.id + "_" + detail['op_def'].operation_name)
                
                of_to_schedule.scheduled_start_date = current_of_scheduled_start_date
                of_to_schedule.scheduled_end_date = current_of_scheduled_end_date # End of the last operation

                # Étape 6 – Mise à jour du statut de l’OF
                # Check if the scheduled start is within the allowed advance/retreat window from the need date
                latest_boundary_date_final = latest_start_date_boundary_for_first_op.date() if isinstance(latest_start_date_boundary_for_first_op, datetime) else latest_start_date_boundary_for_first_op
                earliest_boundary_date_final = earliest_start_date_boundary.date() if isinstance(earliest_start_date_boundary, datetime) else earliest_start_date_boundary
                if (earliest_boundary_date_final <= of_to_schedule.scheduled_start_date.date() <= latest_boundary_date_final): # MODIFIED
                    of_to_schedule.status = "PLANNED"
                    print(f"    OF {of_to_schedule.id} PLANNED. Start: {of_to_schedule.scheduled_start_date.strftime('%Y-%m-%d %H:%M')}, End: {of_to_schedule.scheduled_end_date.strftime('%Y-%m-%d %H:%M')}")
                else:
                    # This case should ideally be caught by the boundary checks during slot finding for the first op
                    of_to_schedule.status = "PLANNED_OUTSIDE_WINDOW"
                    print(f"    OF {of_to_schedule.id} PLANNED_OUTSIDE_WINDOW. Need: {of_to_schedule.need_date.strftime('%Y-%m-%d')}, Start: {of_to_schedule.scheduled_start_date.strftime('%Y-%m-%d %H:%M')}")
            
            else: # Not possible_to_schedule_of or no ops scheduled
                # If scheduling failed, ensure no partial bookings remain (already handled by not booking until all ops are checked)
                of_to_schedule.status = "FAILED_PLANNING"
                print(f"    OF {of_to_schedule.id} FAILED_PLANNING (could not schedule all operations).")

            all_scheduled_ofs.append(of_to_schedule)

    # Update the original list of OFs with the new statuses and dates
    # Create a map for quick updates
    final_of_map = {of.id: of for of in all_scheduled_ofs}
    updated_all_ofs = []
    for original_of in all_ofs_with_groups:
        if original_of.id in final_of_map:
            updated_all_ofs.append(final_of_map[original_of.id])
        else:
            # This OF was not in any group processed by smoothing (should not happen if all_ofs_with_groups is correct)
            # or was not handled (e.g. if it wasn't in ofs_in_group_sorted)
            updated_all_ofs.append(original_of) 
            if original_of.assigned_group_id and original_of.status not in ["PLANNED", "FAILED_PLANNING", "FAILED_PLANNING_NO_OPS", "PLANNED_OUTSIDE_WINDOW"]:
                 print(f"Warning: OF {original_of.id} was in a group but not processed by smoothing loop. Status: {original_of.status}")


    return updated_all_ofs


# --- I/O Functions ---
def load_ofs_from_file(filepath):
    print(f"Loading OFs from {filepath}")
    ofs = []
    try:
        with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
            # Auto-detect delimiter: comma for test files, tab for main files
            delimiter = ',' if 'test_' in filepath else '\t'
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            # Expected columns from input: Part, Description, Order Code, FG, CAT US FS, Qty, Date
            # Mapping to ManufacturingOrder attributes:
            # Part -> product_id
            # Description -> designation
            # Order Code -> id
            # FG -> fg
            # CAT US FS -> cat (this will also be bom_level)
            # Qty -> quantity
            # Date -> need_date_str
            # product_type is derived from Part's prefix
            # us, fs are defaulted to "1" if not otherwise specified

            # Check for essential columns based on the new input format
            # Adjust fieldnames if they are different in the actual CSV header
            expected_input_cols = ["Part", "Description", "Order Code", "FG", "CAT US FS", "Qty", "Date"]
            if not reader.fieldnames:
                print(f"Warning: CSV file {filepath} appears to be empty or header is missing.")
                return []
            
            # Normalize fieldnames: remove leading/trailing spaces and make case-insensitive for matching
            header_map = {col.strip().lower(): col.strip() for col in reader.fieldnames}
            
            mapped_expected_cols = {}
            missing_cols = []
            for col_name in expected_input_cols:
                mapped_col_name = header_map.get(col_name.lower())
                if mapped_col_name:
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

                    cat_us_fs_raw = row[mapped_expected_cols["CAT US FS"]]
                    cat_us_fs_parts = cat_us_fs_raw.split()

                    cat_val = ""
                    us_val = "1" # Default
                    fs_val = "1" # Default

                    if len(cat_us_fs_parts) == 3:
                        cat_val = cat_us_fs_parts[0]
                        us_val = cat_us_fs_parts[1]
                        fs_val = cat_us_fs_parts[2]
                    elif len(cat_us_fs_parts) == 1:
                        cat_val = cat_us_fs_parts[0]
                    elif len(cat_us_fs_parts) > 0: # Handles 2 parts or >3 parts by taking the first as CAT
                        cat_val = cat_us_fs_parts[0]
                        print(f"Warning: Row {row_num}: CAT US FS column ('{cat_us_fs_raw}') has an unexpected number of parts ({len(cat_us_fs_parts)}). Using '{cat_val}' as CAT, defaulting US/FS to '1'.")
                    else: # Empty CAT US FS
                        print(f"Warning: Row {row_num}: CAT US FS column is empty. Defaulting CAT to empty, US/FS to '1'.")
                        cat_val = "" # Or some other default if preferred

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
                        # unit is not in the provided input, defaults in class
                    )
                    ofs.append(of)
                except KeyError as e:
                    print(f"Warning: Missing key {e} in row {row_num} of {filepath}. Row: {row}. Check column names in CSV vs expected_input_cols.")
                except ValueError as e:
                    print(f"Warning: Value error processing row {row_num} of {filepath}: {e}. Row: {row}")
                except Exception as e:
                    print(f"Warning: Unexpected error processing row {row_num} of {filepath}: {e}. Row: {row}")
    except FileNotFoundError:
        print(f"Error: OFs file not found at {filepath}. Returning empty list.")
        return []
    except ValueError as e: # Catch ValueError from header check
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
            reader = csv.DictReader(csvfile)
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
    # Load Posts
    try:
        with open(filepath_posts, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
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
    
    # Load Post Unavailability
    try:
        with open(filepath_post_unavailability, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
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

    # Load Operations
    # operations_map = { "product_id_or_type": [Operation(...), ...], ... }
    # OR operations_map = { "of_id": [Operation(...), ...], ... }
    # For now, let's assume operations are defined by ProductID or ProductType as a fallback.
    operations_map = defaultdict(list)
    try:
        with open(filepath_operations, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            # Flexible operation key: can be OF_ID, ProductID, or ProductType
            # We'll need to decide on a primary key or try multiple.
            # For this example, let's assume a 'KeyID' (can be ProductID or ProductType) and 'KeyType' (ProductID/ProductType)
            # Or more simply, assume 'ProductID' is the key for operations.
            required_cols_ops = ["ProductID", "OperationName", "PostID", "StandardTimeHours", "Sequence", "Priority"]
            if not all(col in reader.fieldnames for col in required_cols_ops):
                raise ValueError(f"Operations CSV {filepath_operations} missing required columns. Need: {required_cols_ops}, Found: {reader.fieldnames}")

            for row in reader:
                # Using ProductID as the key for operations for now
                key = row.get('ProductID') if row.get('ProductID') else row.get('ProductType', 'UNKNOWN_OP_KEY')
                if key == 'UNKNOWN_OP_KEY':
                    print(f"Skipping operation due to missing ProductID/ProductType: {row}")
                    continue

                op = Operation(
                    product_key=key, # Pass product_key instead of of_id
                    operation_name=row['OperationName'],
                    post_id=row['PostID'],
                    standard_time_hours=float(row['StandardTimeHours']),
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
    
    # Define output header based on the expected output format
    output_header = ["Part", "Description", "Order Code", "FG", "CAT", "US", "FS", "Qty", 
                     "X3 Date", "GRP_FLG", "Start Date", "Delay"]

    with open(filepath, "w", newline='', encoding='utf-8') as f: # Use newline='' for csv writer
        writer = csv.writer(f, delimiter='\t') # Assuming tab-delimited output
        writer.writerow(output_header)

        # First, write OFs that are part of groups
        processed_of_ids_in_groups = set()
        all_component_stocks_summary = {}  # Pour le résumé global
        # Sort groups numerically by ID (GRP1, GRP2, GRP3, ..., GRP10)
        def extract_group_number(group):
            try:
                return int(group.id.replace("GRP", ""))
            except:
                return 0
        
        for group in sorted(grouped_list_data, key=extract_group_number): # Sort groups numerically
            f.write(f"\n# Group ID: {group.id}\n")
            f.write(f"#   Produit PS Principal: {group.ps_product_id}\n")
            f.write(f"#   Fenêtre Temporelle: {group.time_window_start.strftime('%Y-%m-%d')} à {group.time_window_end.strftime('%Y-%m-%d')}\n")
            f.write(f"#   Stock PS Théorique Restant: {group.current_ps_stock_available:.2f}\n")
            # Affichage détaillé des stocks de tous les composants du groupe organisé par niveau BOM
            if hasattr(group, 'component_stocks'):
                # Organiser par type de composant pour un affichage plus clair
                pf_stocks = {}
                sf_stocks = {}
                ps_stocks = {}
                
                for comp_id, stock in group.component_stocks.items():
                    if comp_id.startswith('PF'):
                        pf_stocks[comp_id] = stock
                    elif comp_id.startswith('SF'):
                        sf_stocks[comp_id] = stock
                    elif comp_id.startswith('PS'):
                        ps_stocks[comp_id] = stock
                    else:
                        # Autres composants
                        f.write(f"#   Stock {comp_id} Restant: {stock:.2f}\n")
                
                # Afficher dans l'ordre hiérarchique : PF -> SF -> PS
                for comp_id, stock in sorted(pf_stocks.items()):
                    f.write(f"#   Stock {comp_id} Restant: {stock:.2f}\n")
                for comp_id, stock in sorted(sf_stocks.items()):
                    f.write(f"#   Stock {comp_id} Restant: {stock:.2f}\n")
                for comp_id, stock in sorted(ps_stocks.items()):
                    f.write(f"#   Stock {comp_id} Restant: {stock:.2f}\n")
                    # Mise à jour du résumé global
                    if comp_id not in all_component_stocks_summary:
                        all_component_stocks_summary[comp_id] = 0
                    all_component_stocks_summary[comp_id] += stock
            f.write(f"#   OFs dans ce Groupe:\n")
            
            # Get all OFs that were part of this group from all_ofs_final_state
            ofs_in_this_group = [of for of in all_ofs_scheduled if of.assigned_group_id == group.id]

            for of_obj in sorted(ofs_in_this_group, key=lambda x: (-x.bom_level, x.need_date)):
                desc_parts = of_obj.designation.split()
                processed_description = ""
                if not desc_parts:
                    processed_description = "" # Empty if no words
                elif len(desc_parts) >= 2 and desc_parts[0].upper() == "BATENS":
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"
                elif len(desc_parts) == 1:
                    processed_description = desc_parts[0]
                else: # Handles 2 or more words, not starting with BATENS, or exactly 2 words
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"

                processed_order_code = of_obj.id[:10]

                # GRP_FLG: remove "GRP" prefix
                grp_flg = of_obj.assigned_group_id.replace("GRP", "") if of_obj.assigned_group_id else ""
                
                # Start Date
                start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""
                
                # Delay calculation
                delay_val = ""
                if of_obj.scheduled_start_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))
                # else: # scheduled_start_date or need_date is None, delay_val remains ""

                row_to_write = [
                    of_obj.product_id,
                    processed_description,
                    processed_order_code,
                    of_obj.fg,
                    of_obj.cat,
                    of_obj.us,
                    of_obj.fs,
                    int(of_obj.quantity), # Assuming Qty should be integer in output
                    of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                    grp_flg,
                    start_date_str,
                    delay_val
                ]
                writer.writerow(row_to_write)
                processed_of_ids_in_groups.add(of_obj.id)
        
        # Write OFs not assigned to any group (if any)
        # The example output doesn't show a separate section for unassigned OFs in this specific table format
        # So, we will list all OFs from all_ofs_final_state, ensuring each OF is written once.
        # The sorting of groups above and then iterating all_ofs_final_state might lead to OFs being written
        # under their group comments, and then potentially again if we just iterate all_ofs_final_state.
        # The current loop structure writes OFs under their group.
        # If an OF is NOT in any group, it won't be written by the loop above.
        # Let's add a section for OFs that were not in any group.

        f.write("\\n# OFs Non Affectés (pas dans un groupe ou non planifiés avec un groupe):\\n")
        unassigned_ofs_for_output = [of for of in all_ofs_scheduled if of.id not in processed_of_ids_in_groups]

        if not unassigned_ofs_for_output and not grouped_list_data : # If no groups and no unassigned, means all_ofs_final_state is empty or all processed
             pass # Avoid writing header again if all OFs were grouped.
        elif unassigned_ofs_for_output : # Only write if there are truly unassigned OFs to list here
            # writer.writerow(output_header) # Header already written once
            for of_obj in sorted(unassigned_ofs_for_output, key=lambda x: x.id):
                desc_parts = of_obj.designation.split()
                processed_description = ""
                if not desc_parts:
                    processed_description = ""
                elif len(desc_parts) >= 2 and desc_parts[0].upper() == "BATENS":
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"
                elif len(desc_parts) == 1:
                    processed_description = desc_parts[0]
                else:
                    processed_description = f"{desc_parts[0]} {desc_parts[1]}"

                processed_order_code = of_obj.id[:10]
                grp_flg = of_obj.assigned_group_id.replace("GRP", "") if of_obj.assigned_group_id else "" # Should be empty here
                start_date_str = of_obj.scheduled_start_date.strftime("%Y-%m-%d") if of_obj.scheduled_start_date else ""
                
                delay_val = ""
                if of_obj.scheduled_start_date and of_obj.need_date: # Match logic from above for consistency
                    delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))
                # else: delay_val remains ""

                row_to_write = [
                    of_obj.product_id,
                    processed_description,
                    processed_order_code,
                    of_obj.fg,
                    of_obj.cat,
                    of_obj.us,
                    of_obj.fs,
                    int(of_obj.quantity),
                    of_obj.need_date.strftime("%Y-%m-%d") if of_obj.need_date else "",
                    grp_flg, # Likely empty here
                    start_date_str, # Likely empty
                    delay_val
                ]
                writer.writerow(row_to_write)
        
        # The old summary sections are now replaced by the single table output.
        # Remove old f.write sections for "STATUT FINAL DE TOUS LES OFs" if they are redundant with the new table.
        # The current structure aims to produce one consolidated table.

    print(f"Output written to {filepath} with new format.")
    # Old detailed print to console, can be removed or kept for debugging.
    # print("\\n--- STATUT FINAL DE TOUS LES OFs (après lissage) ---")
    # for of in sorted(all_ofs_final_state, key=lambda x: x.id):
    #     print(f"  ID: {of.id}, Desig: {of.designation}, Grp: {of.assigned_group_id}, "
    #           f"Need: {of.need_date.strftime('%Y-%m-%d') if of.need_date else 'N/A'}, "
    #           f"SchedStart: {of.scheduled_start_date.strftime('%Y-%m-%d') if of.scheduled_start_date else 'N/A'}, "
    #           f"Status: {of.status}")


# --- Compact Input Loader ---
import os
def load_compact_input_file(filepath):
    """
    Charge un fichier d'entrée compact où les OFs et la nomenclature sont dans un seul fichier tabulé.
    Format attendu :
    - Les lignes OFS commencent par 'OFS' (ou un autre identifiant, à adapter si besoin)
    - Les lignes nomenclature commencent par 'BOM' (ou un autre identifiant)
    - Les colonnes sont séparées par des tabulations
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
                # Format: OFS\tOrder Code\tDescription\tPart\tFG\tCAT\tUS\tFS\tQty\tDate
                # Adapt if your compact file has a different order
                try:
                    _, of_id, designation, product_id, fg, cat, us, fs, qty, need_date = parts[:10]
                    # Déduire le type produit
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
                # Format: BOM\tParentProductID\tChildProductID\tQuantityChildPerParent\tChildBOMLevel
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
    # Chemins par défaut - UTILISATION DES DONNÉES DE TEST
    compact_file = "input_compact.txt"
    ofs_file = "test_besoins.csv"
    bom_file = "test_nomenclature.csv"
    posts_file = "test_posts.csv"
    post_unavailability_file = "post_unavailability.csv"
    operations_file = "test_operations.csv"
    output_file = "test_besoins_groupes_output.txt"

    # Mode compact si le fichier existe
    if os.path.exists(compact_file):
        print(f"Mode compact détecté : chargement depuis {compact_file}")
        all_ofs, bom_data = load_compact_input_file(compact_file)
    else:
        print("Mode classique : chargement des fichiers CSV classiques.")
        all_ofs = load_ofs_from_file(ofs_file)
        bom_data = load_bom_from_file(bom_file)

    # Chargement des ressources atelier
    posts_map, operations_map = load_posts_and_operations_data(posts_file, post_unavailability_file, operations_file)

    # Paramètres (peuvent être adaptés)
    params = {
        "advance_retreat_weeks": ADVANCE_RETREAT_WEEKS
    }

    # 1. Groupement
    groups, all_ofs_with_groups = run_grouping_algorithm(all_ofs, bom_data, HORIZON_H_WEEKS)

    # 2. Lissage et ordonnancement
    all_ofs_scheduled = smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params)

    # 3. Écriture du résultat
    write_grouped_needs_to_file(output_file, groups, all_ofs_scheduled)

    print(f"\nTraitement terminé. Résultat écrit dans {output_file}.")
