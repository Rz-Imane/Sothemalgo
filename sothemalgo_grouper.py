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

        # stock résiduel de ce produit, calculé après conso nomenclature
        self.individual_product_stock = 0

    def __repr__(self):
        return (
            f"OF(id={self.id}, desig='{self.designation}', prod_id='{self.product_id}', "
            f"type='{self.product_type}', level={self.bom_level}, "
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

        # Niveau BOM de l'enfant
        try:
            self.child_bom_level = int(child_bom_level) if child_bom_level not in (None, "") else 0
        except Exception:
            self.child_bom_level = 0

        # Nouveau : niveau BOM du parent (optionnel)
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
        """
        Nouveau calcul de stock adapté à la logique "on commence par le plus haut niveau BOM".

        Pour chaque groupe :
          1. On calcule la quantité produite par produit (somme des OFs du groupe).
          2. On initialise le stock de chaque produit avec sa quantité produite.
          3. Pour chaque relation de nomenclature (parent -> composant) :
                consommation_enfant = qty_produite_parent * qty_child_per_parent
             On soustrait cette consommation du stock du composant.
          4. On distribue le stock net par produit sur les OFs correspondants (FIFO sur la date besoin).

        Remplit :
          - self.component_stocks : stock net par produit (production - consommation)
          - self.individual_product_stocks : stock net par produit dans le groupe
          - of.individual_product_stock : stock affecté à chaque OF
        """

        from collections import defaultdict

        def norm(x: str) -> str:
            if x is None:
                return ""
            s = str(x).replace('\ufeff', '')
            s = ''.join(s.split())
            return s.upper()

        if not self.ofs:
            self.component_stocks = {}
            self.individual_product_stocks = {}
            return

        # -------------------------------------------------
        # 1. Niveaux BOM par produit (ChildBOMLevel / ParentBOMLevel + fallback OF.bom_level)
        # -------------------------------------------------
        product_level = {}

        # Niveaux provenant de la nomenclature
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
                # plus le niveau est élevé, plus le composant est "profond"
                product_level[c] = c_lvl if c not in product_level else max(product_level[c], c_lvl)
            if p and p_lvl > 0:
                product_level[p] = p_lvl if p not in product_level else max(product_level[p], p_lvl)

        # Produits présents dans ce groupe
        group_products = {norm(of.product_id) for of in self.ofs}

        # Fallback : si certains produits du groupe n'ont pas de niveau dans le BOM,
        # on utilise leur bom_level issu du fichier besoins (colonne CAT).
        for pid in group_products:
            if pid not in product_level:
                # On prend n'importe quel OF de ce produit
                of0 = next(of for of in self.ofs if norm(of.product_id) == pid)
                try:
                    lvl = int(getattr(of0, "bom_level", 0) or 0)
                except Exception:
                    lvl = 0
                product_level[pid] = lvl

        # -------------------------------------------------
        # 2. Quantités produites par produit (somme des OFs de ce groupe)
        # -------------------------------------------------
        produced_qty = defaultdict(float)
        for of in self.ofs:
            pid = norm(of.product_id)
            produced_qty[pid] += float(of.quantity)

        if not produced_qty:
            self.component_stocks = {}
            self.individual_product_stocks = {}
            for of in self.ofs:
                of.individual_product_stock = 0.0
            return

        # Liste des niveaux présents dans le groupe
        levels_in_group = {product_level.get(pid, 0) for pid in produced_qty.keys()}
        max_level = max(levels_in_group) if levels_in_group else 0
        min_level = min(levels_in_group) if levels_in_group else 0

        # -------------------------------------------------
        # 3. Construction du BOM par parent (dans le contexte du groupe)
        # -------------------------------------------------
        bom_by_parent = defaultdict(list)
        for bom in bom_data:
            p = norm(bom.parent_product_id)
            c = norm(bom.child_product_id)
            if not p or not c:
                continue
            # On ne considère la conso que si le parent existe dans le groupe
            if p in produced_qty:
                bom_by_parent[p].append((c, float(bom.quantity_child_per_parent)))

        # -------------------------------------------------
        # 4. Calcul du stock net par produit (niveau le plus élevé -> niveau le plus faible)
        # -------------------------------------------------
        product_stock = {pid: 0.0 for pid in produced_qty.keys()}
        product_consumption = defaultdict(float)

        # On parcourt les niveaux du plus "profond" (composant) vers le plus "haut" (PF)
        # pour respecter l'idée "on produit d'abord les niveaux les plus élevés".
        for lvl in range(max_level, min_level - 1, -1):
            # Tous les produits à ce niveau
            for pid, plvl in product_level.items():
                if plvl != lvl:
                    continue
                if pid not in produced_qty:
                    continue  # pas d'OF pour ce produit dans ce groupe

                qty_prod = produced_qty[pid]
                if qty_prod <= 0:
                    continue

                # On "produit" ce niveau : le stock de ce produit augmente de sa quantité produite
                product_stock[pid] = product_stock.get(pid, 0.0) + qty_prod

                # Puis on consomme ses composants selon la nomenclature
                for child_id, q_child in bom_by_parent.get(pid, []):
                    # Conso seulement si le composant existe dans le groupe
                    if child_id not in produced_qty:
                        continue
                    need = qty_prod * q_child
                    product_stock[child_id] = product_stock.get(child_id, 0.0) - need
                    product_consumption[child_id] += need

        # -------------------------------------------------
        # 5. Répartition du stock net par produit sur les OFs (FIFO sur date besoin)
        # -------------------------------------------------
        remaining_per_of = {of.id: 0.0 for of in self.ofs}

        for prod_norm in produced_qty.keys():
            stock_left = max(0.0, product_stock.get(prod_norm, 0.0))

            # Tous les OFs de ce produit dans le groupe
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

        # Mise à jour des champs OF + synthèse groupe
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
        # component_stocks = stock net par produit (production - consommation totale)
        self.component_stocks = dict(product_stock)


class Post:
    def __init__(
        self,
        id,
        name,
        default_capacity_hours_week=35,
        work_start_time_config=time(8, 0),
        work_end_time_config=time(17, 0),
        lunch_start_time_config=time(12, 0),
        lunch_end_time_config=time(13, 0)
    ):
        self.id = id
        self.name = name
        self.work_start_time = work_start_time_config
        self.work_end_time = work_end_time_config
        self.lunch_start_time = lunch_start_time_config
        self.lunch_end_time = lunch_end_time_config

        ws = datetime.combine(date.min, self.work_start_time)
        we = datetime.combine(date.min, self.work_end_time)
        ls = datetime.combine(date.min, self.lunch_start_time)
        le = datetime.combine(date.min, self.lunch_end_time)

        self.daily_capacity_hours = 0
        if we > ws:
            total_work_seconds = (we - ws).total_seconds()
            lunch_seconds = 0
            if le > ls and ls >= ws and le <= we:
                actual_lunch_start = max(ws, ls)
                actual_lunch_end = min(we, le)
                if actual_lunch_end > actual_lunch_start:
                    lunch_seconds = (actual_lunch_end - actual_lunch_start).total_seconds()
            self.daily_capacity_hours = (total_work_seconds - lunch_seconds) / 3600.0
            if self.daily_capacity_hours < 0:
                self.daily_capacity_hours = 0

        self.unavailable_periods = []
        self.scheduled_slots = []

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
                if current_dt.weekday() >= 5:
                    current_dt = (current_dt + timedelta(days=1)).replace(
                        hour=self.work_start_time.hour,
                        minute=self.work_start_time.minute
                    )
                    continue
                moved = False
                for un_start, un_end in self.unavailable_periods:
                    if un_start.date() <= current_dt.date() <= un_end.date():
                        if current_dt < un_end:
                            current_dt = (un_end + timedelta(minutes=1)).replace(
                                hour=self.work_start_time.hour,
                                minute=self.work_start_time.minute
                            )
                            moved = True
                            break
                if not moved:
                    break

            current_time = current_dt.time()
            if current_time >= self.work_end_time:
                current_dt = (current_dt + timedelta(days=1)).replace(
                    hour=self.work_start_time.hour,
                    minute=self.work_start_time.minute
                )
                continue
            if current_time < self.work_start_time:
                current_dt = current_dt.replace(
                    hour=self.work_start_time.hour,
                    minute=self.work_start_time.minute
                )

            current_time = current_dt.time()
            if self.lunch_start_time <= current_time < self.lunch_end_time:
                current_dt = current_dt.replace(
                    hour=self.lunch_end_time.hour,
                    minute=self.lunch_end_time.minute
                )
                continue

            for un_start, un_end in self.unavailable_periods:
                if un_start <= current_dt < un_end:
                    current_dt = un_end
                    break

            if self._is_working_moment(current_dt):
                return current_dt
            current_dt += timedelta(minutes=1)

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
                continue
            next_minute_dt = current_dt + timedelta(minutes=1)
            seconds_this_minute = 60
            can_consume_seconds = min(remaining_seconds, seconds_this_minute)
            remaining_seconds -= can_consume_seconds
            current_dt = next_minute_dt
        if remaining_seconds > 0:
            return datetime.max
        return current_dt

    def find_available_slot(self, search_start_dt_param, duration_hours, of_id_to_ignore=None):
        current_try_start_dt = self._get_next_working_datetime(search_start_dt_param)
        max_search_datetime = search_start_dt_param + timedelta(days=180)
        while current_try_start_dt < max_search_datetime:
            potential_end_dt = self.calculate_end_datetime(current_try_start_dt, duration_hours)
            if potential_end_dt == datetime.max:
                current_try_start_dt = (current_try_start_dt + timedelta(days=1)).replace(
                    hour=self.work_start_time.hour,
                    minute=self.work_start_time.minute
                )
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
        return None, None

    def book_slot(self, start_dt, end_dt, of_id):
        self.clear_schedule_for_of(of_id)
        self.scheduled_slots.append((start_dt, end_dt, of_id))
        self.scheduled_slots.sort()

    def clear_schedule_for_of(self, of_id):
        self.scheduled_slots = [
            (s, e, o) for (s, e, o) in self.scheduled_slots if o != of_id
        ]

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
    return sorted(of_list, key=lambda of: (of.designation, -of.bom_level, of.need_date))


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
    """
    Regroupement adapté :
      - On commence par les produits ayant le BOM level le PLUS ÉLEVÉ
        (premiers composants / plus profonds dans la nomenclature).
      - On ne crée un groupe que si, dans les candidats, il existe au moins
        une relation parent–enfant (ParentProductID -> ChildProductID) entre
        deux produits présents dans le groupe.
      - Les OF sans relation parent–enfant restent non affectés (OFs Non Affectés).
    """
    group_counter = 1
    groups = []
    skipped = set()

    def norm(x):
        return ''.join(str(x or '').split()).upper()

    # Graphe produit <-> composant (non orienté) pour trouver la famille BOM
    bom_graph = build_bom_graph(bom_data)

    # -----------------------------
    # 1. Calcul du niveau BOM par produit (ChildBOMLevel / ParentBOMLevel + fallback OF.bom_level)
    # -----------------------------
    product_level = {}

    for b in bom_data:
        p = norm(b.parent_product_id)
        c = norm(b.child_product_id)

        # niveau enfant
        try:
            c_lvl = int(getattr(b, "child_bom_level", 0) or 0)
        except Exception:
            c_lvl = 0

        # niveau parent (optionnel)
        try:
            p_lvl = int(getattr(b, "parent_bom_level", 0) or 0)
        except Exception:
            p_lvl = 0

        if c and c_lvl > 0:
            # plus le niveau est élevé, plus le composant est "profond"
            product_level[c] = c_lvl if c not in product_level else max(product_level[c], c_lvl)
        if p and p_lvl > 0:
            product_level[p] = p_lvl if p not in product_level else max(product_level[p], p_lvl)

    # fallback : si certains produits n'ont pas de niveau dans la nomenclature,
    # on utilise le bom_level des OFs (colonne CAT du fichier besoins).
    for of in all_ofs:
        pid = norm(of.product_id)
        if pid not in product_level:
            try:
                lvl = int(getattr(of, "bom_level", 0) or 0)
            except Exception:
                lvl = 0
            product_level[pid] = lvl

    # 1bis – stocker le niveau BOM effectif sur chaque OF
    for of in all_ofs:
        pid = norm(of.product_id)
        lvl = product_level.get(pid, getattr(of, "bom_level", 0) or 0)
        try:
            of.effective_bom_level = int(lvl)
        except Exception:
            of.effective_bom_level = 0

    def get_level(of):
        try:
            return int(
                getattr(of, "effective_bom_level", None)
                if getattr(of, "effective_bom_level", None) is not None
                else getattr(of, "bom_level", 0) or 0
            )
        except Exception:
            return 0

    # -----------------------------
    # 2. Choix de l'ancre : OF non affecté ayant le niveau BOM le plus ÉLEVÉ
    # -----------------------------
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

    # -----------------------------
    # 3. Boucle principale de regroupement
    # -----------------------------
    while True:
        anchor_of = first_unassigned_highest_level()
        if anchor_of is None:
            break  # plus d'OF à traiter

        anchor_pid_norm = norm(anchor_of.product_id)

        # Famille de produits connectés à l'ancre dans la nomenclature
        family = connected_component_nodes(bom_graph, anchor_of.product_id)
        if not family:
            family = {anchor_pid_norm}

        # Fenêtre temporelle [date besoin ancre, +H semaines]
        window_start_date = anchor_of.need_date
        window_end_date = window_start_date + timedelta(weeks=horizon_H_weeks_param) - timedelta(days=1)

        # Candidats bruts = OF non encore affectés, même famille BOM, dans la fenêtre
        raw_candidates = [
            of
            for of in all_ofs
            if (
                of.assigned_group_id is None
                and window_start_date <= of.need_date <= window_end_date
                and norm(of.product_id) in family
            )
        ]

        # -----------------------------------
        # Filtrage : on ne garde que les OF dont le produit
        # a au moins une relation parent–enfant avec un autre produit
        # parmi les candidats (d'après la nomenclature).
        # -----------------------------------
        cand_pids_raw = {norm(of.product_id) for of in raw_candidates}
        related_pids = set()

        for b in bom_data:
            p = norm(b.parent_product_id)
            c = norm(b.child_product_id)
            # Parent et enfant présents tous les deux dans les candidats ?
            if p in cand_pids_raw and c in cand_pids_raw:
                related_pids.add(p)
                related_pids.add(c)

        # On garde uniquement les OF dont le produit est dans related_pids
        candidates = [
            of for of in raw_candidates
            if norm(of.product_id) in related_pids
        ]

        # Si aucun couple parent–enfant, ou un seul OF, on ne crée pas de groupe
        if len(candidates) <= 1:
            skipped.add(anchor_of.id)
            continue

        # Si l'ancre ne fait pas partie des produits reliés (parent–enfant),
        # on ne crée pas de groupe avec elle comme ancre.
        if anchor_of not in candidates:
            skipped.add(anchor_of.id)
            continue

        # Création du groupe : l'ancre sert de "PS principal" (logique interne du modèle)
        current_group = Group(
            id=f"GRP{group_counter}",
            ps_product_id=anchor_of.product_id,
            initial_ps_of=anchor_of,
            window_start_date=window_start_date,
            window_end_date=window_end_date,
            initial_ps_as_stock=False,  # le stock sera recalculé par calculate_consumption
        )

        # On ajoute les autres OF du groupe : on commence par les BOM levels les plus élevés
        def sort_key(of):
            return (-get_level(of), of.need_date, of.product_id)

        for ofx in sorted(candidates, key=sort_key):
            if ofx.id == anchor_of.id:
                continue  # déjà ajouté par le constructeur du groupe
            current_group.add_of(ofx, ps_quantity_change=0)

        # Calcul des consommations / stocks à l’intérieur du groupe (nouvelle logique par niveaux)
        current_group.calculate_consumption(bom_data)

        groups.append(current_group)
        group_counter += 1

    return groups, all_ofs


def smooth_and_schedule_groups(groups, all_ofs_with_groups, bom_data, posts_map, operations_map, params):
    import json

    def dt_to_str(dt):
        return dt.strftime("%Y-%m-%d %H:%M") if dt else None

    def days_delay_if_late(scheduled_start_dt, need_dt):
        if scheduled_start_dt is None:
            return 0
        delta = (scheduled_start_dt.date() - need_dt.date()).days
        return delta if delta > 0 else 0

    advance_retreat_weeks = int(params.get("advance_retreat_weeks", 3))
    adv_td = timedelta(weeks=advance_retreat_weeks)

    smoothing_json_path = params.get("smoothing_json_path")
    if not smoothing_json_path:
        uploads = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads, exist_ok=True)
        smoothing_json_path = os.path.join(uploads, "smoothing_view.json")

    smoothing_items = []
    scheduled_ofs = []

    def find_first_op_two_phase(post_obj, need_dt, op_hours, group_start_date):
        ADV_WEEKS = 3
        adv_td_local = timedelta(weeks=ADV_WEEKS)

        g_start = (
            group_start_date
            if isinstance(group_start_date, datetime)
            else datetime.combine(group_start_date, time.min)
        )
        need_d = need_dt.date()
        hi_d = (need_dt + adv_td_local).date()

        a_start = max(g_start, need_dt - adv_td_local)
        a_start = post_obj._get_next_working_datetime(a_start)
        s, e = post_obj.find_available_slot(a_start, op_hours, of_id_to_ignore=None)
        if s and e and s.date() <= need_d:
            return s, e

        next_day_midnight = datetime.combine(need_d + timedelta(days=1), time.min)
        b_start = post_obj._get_next_working_datetime(max(next_day_midnight, g_start))
        if b_start.date() <= hi_d:
            s, e = post_obj.find_available_slot(b_start, op_hours, of_id_to_ignore=None)
            if s and e and (need_d < s.date() <= hi_d):
                return s, e

        return None, None

    for group in sorted(groups, key=lambda g: g.time_window_start):
        ofs_sorted = sorted(
            [of for of in all_ofs_with_groups if of.assigned_group_id == group.id],
            key=lambda x: (-x.bom_level, x.need_date)
        )

        for of_to_schedule in ofs_sorted:
            ops = operations_map.get(of_to_schedule.product_id, []) or operations_map.get(
                of_to_schedule.product_type, []
            )
            if not ops:
                of_to_schedule.status = "ÉCHOUÉ"
                of_to_schedule.scheduled_start_date = None
                of_to_schedule.scheduled_end_date = None
                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": of_to_schedule.need_date.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": "ÉCHOUÉ",
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
                if i == 0:
                    s_dt, e_dt = find_first_op_two_phase(
                        post, of_to_schedule.need_date, dur_h, group.time_window_start
                    )
                else:
                    start_search = post._get_next_working_datetime(last_end)
                    s_dt, e_dt = post.find_available_slot(
                        start_search,
                        dur_h,
                        of_id_to_ignore=of_to_schedule.id + "_" + op_def.operation_name,
                    )

                if s_dt and e_dt:
                    op_sched.append((op_def, post, s_dt, e_dt))
                    last_end = e_dt
                else:
                    feasible = False
                    fail_reason = (
                        "No slot in allowed windows"
                        if i == 0
                        else f"No slot for '{op_def.operation_name}' after {last_end}"
                    )
                    break

            if feasible and op_sched:
                for op_def, post, s_dt, e_dt in op_sched:
                    post.book_slot(s_dt, e_dt, of_to_schedule.id + "_" + op_def.operation_name)

                start_dt = op_sched[0][2]
                end_dt = op_sched[-1][3]
                of_to_schedule.scheduled_start_date = start_dt
                of_to_schedule.scheduled_end_date = end_dt

                need_d = of_to_schedule.need_date.date()
                hi_d = (of_to_schedule.need_date + timedelta(weeks=3)).date()
                start_d = start_dt.date()

                if start_d <= need_d:
                    statut = "OUI"
                elif need_d < start_d <= hi_d:
                    statut = "NON"
                else:
                    statut = "ÉCHOUÉ"

                of_to_schedule.status = statut
                retard_jours = days_delay_if_late(start_dt, of_to_schedule.need_date)

                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": of_to_schedule.need_date.strftime("%Y-%m-%d"),
                        "scheduled_start": dt_to_str(start_dt),
                        "scheduled_end": dt_to_str(end_dt),
                        "status": statut,
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
                of_to_schedule.status = "ÉCHOUÉ"
                of_to_schedule.scheduled_start_date = None
                of_to_schedule.scheduled_end_date = None
                smoothing_items.append(
                    {
                        "of_id": of_to_schedule.id,
                        "product_id": of_to_schedule.product_id,
                        "designation": of_to_schedule.designation,
                        "group_id": group.id,
                        "need_date": of_to_schedule.need_date.strftime("%Y-%m-%d"),
                        "scheduled_start": None,
                        "scheduled_end": None,
                        "status": "ÉCHOUÉ",
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

    return updated_all


def write_grouped_needs_to_file(filepath, grouped_list_data, all_ofs_scheduled):
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

    def is_premix(of_obj):
        name = (of_obj.designation or "").strip().upper()
        return name.startswith("PREMIX")

    def display_class(of_obj):
        # tu peux garder ça si tu veux encore distinguer PF / SF / PREMIX
        if is_premix(of_obj):
            return 2
        if of_obj.product_type == "PF":
            return 0
        return 1

    def get_bom_level(of_obj):
        """Niveau BOM effectif pour le tri (décroissant)."""
        try:
            return int(
                getattr(of_obj, "effective_bom_level", None)
                if getattr(of_obj, "effective_bom_level", None) is not None
                else getattr(of_obj, "bom_level", 0) or 0
            )
        except Exception:
            return 0

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(output_header)

        processed_of_ids_in_groups = set()

        def extract_group_number(group):
            try:
                return int(group.id.replace("GRP", ""))
            except Exception:
                return 0

        # -----------------------------
        # Écriture des OF par groupe
        # -----------------------------
        for group in sorted(grouped_list_data, key=extract_group_number):
            f.write(f"\n# Group ID: {group.id}\n")
            f.write(f"#   Produit PS Principal (ancre): {group.ps_product_id}\n")
            f.write(
                f"#   Fenêtre Temporelle: "
                f"{group.time_window_start.strftime('%Y-%m-%d')} à "
                f"{group.time_window_end.strftime('%Y-%m-%d')}\n"
            )

            if hasattr(group, "individual_product_stocks") and group.ps_product_id in group.individual_product_stocks:
                f.write(
                    f"#   Stock PS Calculé: "
                    f"{group.individual_product_stocks[group.ps_product_id]}\n"
                )
            else:
                f.write("#   Stock PS: Non calculé / Ancre composant\n")

            ofs_in_group = [of for of in all_ofs_scheduled if of.assigned_group_id == group.id]

            # Ordre DÉCROISSANT sur le niveau BOM :
            #   niveau le plus élevé en haut, plus faible en bas
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
                delay_val = ""
                if of_obj.scheduled_start_date and of_obj.need_date:
                    delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                    delay_val = str(max(0, delay_days))

                stock_val = getattr(of_obj, "individual_product_stock", None)
                if stock_val is None:
                    stock_val = getattr(of_obj, "remaining_stock", 0.0)
                if stock_val is None:
                    stock_val = 0.0

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

        # -----------------------------
        # OFs Non Affectés
        # -----------------------------
        f.write("\n# OFs Non Affectés:\n")
        unassigned = [of for of in all_ofs_scheduled if of.id not in processed_of_ids_in_groups]

        # Même ordre décroissant pour les non affectés
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
            delay_val = ""
            if of_obj.scheduled_start_date and of_obj.need_date:
                delay_days = (of_obj.scheduled_start_date - of_obj.need_date).days
                delay_val = str(max(0, delay_days))

            stock_val = getattr(of_obj, "individual_product_stock", None)
            if stock_val is None:
                stock_val = getattr(of_obj, "remaining_stock", 0.0)
            if stock_val is None:
                stock_val = 0.0

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

                try:
                    bom_level_derived = int(cat_val) if cat_val else 0
                except ValueError:
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

    # Colonnes obligatoires
    required_cols = [
        "ParentProductID",
        "ChildProductID",
        "QuantityChildPerParent",
        "ChildBOMLevel",
    ]

    # + alias, avec ParentBOMLevel en option
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
        # Nouveau : ParentBOMLevel optionnel
        "ParentBOMLevel": ["parentbomlevel", "parent level", "niveau parent"],
    }

    def _alias_map(fieldnames):
        lower = {c.strip().lower(): c.strip() for c in (fieldnames or [])}
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

    # Détection optionnelle de la colonne ParentBOMLevel
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
        with open(filepath_posts, mode="r", encoding="utf-8-sig") as csvfile:
            delimiter = detect_csv_delimiter(filepath_posts, fallback=",")
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols_posts = ["PostID", "PostName", "DefaultCapacityHoursWeek"]
            if not reader.fieldnames or not all(col in reader.fieldnames for col in required_cols_posts):
                available_cols = reader.fieldnames if reader.fieldnames else []
                raise ValueError(
                    f"Posts CSV {filepath_posts} missing required columns. "
                    f"Need: {required_cols_posts}, Found: {available_cols}"
                )
            for row in reader:
                post = Post(
                    id=row["PostID"],
                    name=row["PostName"],
                    default_capacity_hours_week=int(row["DefaultCapacityHoursWeek"]),
                )
                posts_map[post.id] = post
    except FileNotFoundError:
        print(f"Warning: Posts file not found at {filepath_posts}. Using empty posts_map.")
    except Exception as e:
        print(f"Error loading Posts from {filepath_posts}: {e}")

    try:
        if filepath_post_unavailability and os.path.isfile(filepath_post_unavailability):
            with open(filepath_post_unavailability, mode="r", encoding="utf-8-sig") as csvfile:
                delimiter = detect_csv_delimiter(filepath_post_unavailability, fallback=",")
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                required_cols_unavail = ["PostID", "UnavailableStartDate", "UnavailableEndDate"]
                if not reader.fieldnames or not all(col in reader.fieldnames for col in required_cols_unavail):
                    pass
                else:
                    for row in reader:
                        pid = row.get("PostID", "")
                        if (
                            pid in posts_map
                            and row.get("UnavailableStartDate")
                            and row.get("UnavailableEndDate")
                        ):
                            posts_map[pid].add_unavailable_period(
                                row["UnavailableStartDate"], row["UnavailableEndDate"]
                            )
        else:
            pass
    except Exception as e:
        print(f"Warning: Failed reading unavailability file {filepath_post_unavailability}: {e}.")

    operations_map = defaultdict(list)
    try:
        with open(filepath_operations, mode="r", encoding="utf-8-sig") as csvfile:
            delimiter = detect_csv_delimiter(filepath_operations, fallback=",")
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            required_cols_ops = [
                "ProductID",
                "OperationName",
                "PostID",
                "StandardTimeHours",
                "Sequence",
                "Priority",
            ]
            if not reader.fieldnames or not all(col in reader.fieldnames for col in required_cols_ops):
                raise ValueError(
                    f"Operations CSV {filepath_operations} missing required columns. "
                    f"Need: {required_cols_ops}, Found: {reader.fieldnames}"
                )
            for row in reader:
                key = row.get("ProductID") if row.get("ProductID") else row.get(
                    "ProductType", "UNKNOWN_OP_KEY"
                )
                if key == "UNKNOWN_OP_KEY":
                    continue
                op = Operation(
                    product_key=key,
                    operation_name=row["OperationName"],
                    post_id=row["PostID"],
                    standard_time_hours=row["StandardTimeHours"],
                    sequence=int(row["Sequence"]),
                    priority=int(row.get("Priority", 1)),
                )
                operations_map[key].append(op)
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
                        # Format compact : BOM parent child qty_per_parent child_level [parent_level? -> à ajouter si tu veux]
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


if __name__ == "__main__":
    compact_file = "input_compact.txt"
    ofs_file = "test_besoins.csv"
    # utilise le fichier client de nomenclature
    bom_file = "test_nomenclature_client.csv"
    posts_file = "test_posts.csv"
    post_unavailability_file = "post_unavailability.csv"
    operations_file = "test_operations.csv"
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

    params = {"advance_retreat_weeks": ADVANCE_RETREAT_WEEKS}

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
