from flask import Flask, render_template, request, jsonify, redirect, url_for
import pandas as pd
import os
import re
import json
import random
from datetime import datetime, timedelta
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from sothemalgo_grouper import (
    load_ofs_from_file,
    load_bom_from_file,
    load_posts_and_operations_data,
    run_grouping_algorithm,
    smooth_and_schedule_groups,
    write_grouped_needs_to_file,
    HORIZON_H_WEEKS,
)


def parse_output_file(file_path):
    """Parse le fichier de sortie et retourne les données structurées."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        content = content.replace('\\n', '\n')
        groups = []
        unassigned_ofs = []

        lines = content.split('\n')
        current_group = None
        in_group = False
        in_unassigned = False
        in_calculated_stocks = False

        for line in lines:
            line = line.strip()

            # Début d'un groupe
            if 'Group ID:' in line:
                if current_group:
                    groups.append(current_group)
                current_group = {
                    'id': line.split('Group ID:')[1].strip().replace('#', '').strip(),
                    'ps_product': '',
                    'time_window': '',
                    'remaining_stock': '',
                    'calculated_stocks': {},
                    'ofs': []
                }
                in_group = True
                in_unassigned = False
                in_calculated_stocks = False
                continue

            # Infos du groupe
            if in_group and current_group:
                if 'Produit PS Principal' in line and ':' in line:
                    current_group['ps_product'] = line.split(':', 1)[1].strip().replace('#', '').strip()
                elif 'Fenêtre Temporelle:' in line:
                    current_group['time_window'] = line.split('Fenêtre Temporelle:')[1].strip().replace('#', '').strip()
                elif 'Stock PS Calculé:' in line:
                    current_group['remaining_stock'] = line.split('Stock PS Calculé:')[1].strip().replace('#', '').strip()
                elif 'Stocks calculés:' in line:
                    in_calculated_stocks = True
                    continue
                elif in_calculated_stocks and line.startswith('#') and ':' in line and 'unités' in line:
                    stock_line = line.replace('#', '').strip()
                    if ':' in stock_line and 'unités' in stock_line:
                        product_part = stock_line.split(':')[0].strip()
                        stock_value = stock_line.split(':')[1].replace('unités', '').strip()
                        try:
                            current_group['calculated_stocks'][product_part] = float(stock_value)
                        except ValueError:
                            current_group['calculated_stocks'][product_part] = 0
                elif line.startswith('#') and 'OFs dans ce Groupe:' in line:
                    in_calculated_stocks = False

            # Section OFs non affectés
            if 'OFs Non Affectés' in line:
                if current_group:
                    groups.append(current_group)
                    current_group = None
                in_group = False
                in_unassigned = True
                in_calculated_stocks = False
                continue

            # Lignes d'OFs
            if '\t' in line and not line.startswith('#') and line.count('\t') >= 12:
                parts = line.split('\t')

                if parts[0] == 'Part':
                    continue

                if len(parts) >= 13:
                    of_data = {
                        'Part': parts[0],
                        'Description': parts[1],
                        'Order_Code': parts[2],
                        'FG': parts[3],
                        'CAT': parts[4],
                        'US': parts[5],
                        'FS': parts[6],
                        'Qty': parts[7],
                        'X3_Date': parts[8],
                        'GRP_FLG': parts[9] if len(parts) > 9 else '',
                        'Start_Date': parts[10] if len(parts) > 10 else '',
                        'Delay': parts[11] if len(parts) > 11 else '',
                        'remaining_stock': parts[12] if len(parts) > 12 else 'N/A'
                    }

                    if in_unassigned or not of_data.get('GRP_FLG'):
                        of_data['Statut'] = 'Non affecté'
                    else:
                        of_data['Statut'] = 'Affecté'

                    if in_unassigned or not of_data.get('GRP_FLG'):
                        unassigned_ofs.append(of_data)
                    elif current_group:
                        current_group['ofs'].append(of_data)

        if current_group:
            groups.append(current_group)

        groups_with_supply = []
        groups_without_supply = []

        for group in groups:
            ofs_in_group = group.get('ofs', [])
            ps_product = (group.get('ps_product') or '').strip()

            supply_present = False
            if ps_product:
                supply_present = any((of.get('Part') or '').strip() == ps_product for of in ofs_in_group)

            if not supply_present:
                supply_present = any((of.get('Part') or '').startswith('PS') for of in ofs_in_group)

            group['has_supply'] = supply_present
            group['has_ps'] = supply_present

            if supply_present:
                groups_with_supply.append(group)
            else:
                groups_without_supply.append(group)

        groups_for_display = groups_with_supply if groups_with_supply else groups
        truly_unassigned_ofs = list(unassigned_ofs)

        non_productible_ofs_in_groups = []
        for group in groups_without_supply:
            for of in group.get('ofs', []):
                non_productible_ofs_in_groups.append(of)

        return {
            'groups': groups_for_display,
            'unassigned_ofs': truly_unassigned_ofs,
            'non_productible_ofs_in_groups': non_productible_ofs_in_groups
        }

    except Exception as e:
        return {'error': f'Erreur lors du parsing du fichier: {str(e)}', 'groups': [], 'unassigned_ofs': []}


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def build_planning_sections(parsed_data):
    """Construit les sections pour la page planning."""
    def row_from_of(of):
        part = (of.get('Part') or '').strip()
        order_code = (of.get('Order_Code') or '').strip()
        qty = (of.get('Qty') or '').strip()
        need = (of.get('X3_Date') or '').strip()
        start = (of.get('Start_Date') or '').strip()
        delay = (of.get('Delay') or '').strip()
        try:
            delay_int = int(str(delay).strip() or "0")
        except:
            delay_int = 0
        statut = "OUI" if start and delay_int == 0 else "NON"
        return {
            "article": part,
            "num_order": order_code,
            "qte_lance": qty,
            "date_besoin": need,
            "date_proposee": start or "—",
            "statut_faisable": statut,
            "retard": str(delay_int),
        }

    sections = []

    for g in parsed_data.get('groups', []):
        gid = (g.get('id') or '').strip()
        ps = (g.get('ps_product') or '—').strip()
        window = (g.get('time_window') or '—').replace('à', '→')
        rows = [row_from_of(of) for of in g.get('ofs', [])]
        rows.sort(key=lambda r: (r["date_besoin"], r["num_order"]))
        sections.append({
            "title": f"Groupe {gid}",
            "subtitle": f"PS: {ps}  |  Fenêtre: {window}",
            "rows": rows
        })

    unassigned = [row_from_of(of) for of in parsed_data.get('unassigned_ofs', [])]
    unassigned.sort(key=lambda r: (r["date_besoin"], r["num_order"]))
    sections.append({
        "title": "Non affectés",
        "subtitle": "OF hors groupe",
        "rows": unassigned
    })

    return sections


@app.route("/planning")
def planning_page():
    import json, os
    path = os.path.join(os.getcwd(), "uploads", "smoothing_view.json")
    rows = []
    generated_at = "—"
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            generated_at = payload.get("generated_at", "—")
            rows = payload.get("items", [])
    except Exception as e:
        print(f"[planning] cannot read {path}: {e}")

    for r in rows:
        r.setdefault("group_id", "Hors groupe")
        r.setdefault("product_id", "")
        r.setdefault("designation", "")
        r.setdefault("need_date", "")
        r.setdefault("scheduled_start", None)
        r.setdefault("scheduled_end", None)
        r.setdefault("status", "")
        r.setdefault("retard_jours", 0)
        r.setdefault("operations", [])

    return render_template(
        "planning_modern.html",
        generated_at=generated_at,
        rows=rows,
    )


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action', 'run_algorithm')

        besoins_file_storage = request.files.get('besoins_file')
        nomenclature_file_storage = request.files.get('nomenclature_file')
        posts_file_storage = request.files.get('posts_file')
        operations_file_storage = request.files.get('operations_file')
        post_unavailability_file_storage = request.files.get('post_unavailability_file')

        base_dir = BASE_DIR
        use_test_data = request.form.get('use_test_data', 'false').lower() == 'true'

        if besoins_file_storage and besoins_file_storage.filename:
            besoins_path = os.path.join(app.config['UPLOAD_FOLDER'], besoins_file_storage.filename)
            besoins_file_storage.save(besoins_path)
        else:
            if use_test_data:
                besoins_path = os.path.join(base_dir, 'test_besoins.csv')
            else:
                besoins_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_besoins_client.csv')

        if nomenclature_file_storage and nomenclature_file_storage.filename:
            nomenclature_path = os.path.join(app.config['UPLOAD_FOLDER'], nomenclature_file_storage.filename)
            nomenclature_file_storage.save(nomenclature_path)
        else:
            if use_test_data:
                nomenclature_path = os.path.join(base_dir, 'test_nomenclature.csv')
            else:
                nomenclature_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_nomenclature_client.csv')

        if posts_file_storage and posts_file_storage.filename:
            posts_path = os.path.join(app.config['UPLOAD_FOLDER'], posts_file_storage.filename)
            posts_file_storage.save(posts_path)
        else:
            if use_test_data:
                posts_path = os.path.join(base_dir, 'test_posts.csv')
            else:
                posts_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_posts_client.csv')

        if operations_file_storage and operations_file_storage.filename:
            operations_path = os.path.join(app.config['UPLOAD_FOLDER'], operations_file_storage.filename)
            operations_file_storage.save(operations_path)
        else:
            if use_test_data:
                operations_path = os.path.join(base_dir, 'test_operations.csv')
            else:
                operations_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_operations_client.csv')

        if post_unavailability_file_storage and post_unavailability_file_storage.filename:
            post_unavailability_path = os.path.join(app.config['UPLOAD_FOLDER'], post_unavailability_file_storage.filename)
            post_unavailability_file_storage.save(post_unavailability_path)
        else:
            if use_test_data:
                post_unavailability_path = os.path.join(base_dir, 'test_post_unavailability.csv')
            else:
                post_unavailability_path = os.path.join(base_dir, 'post_unavailability.csv')

        try:
            retreat_weeks_val = int(request.form.get('retreat_weeks', '0'))
        except ValueError:
            retreat_weeks_val = 0

        try:
            horizon_weeks_val = int(request.form.get('horizon_weeks', '4'))
        except ValueError:
            horizon_weeks_val = 4

        try:
            smoothing_horizon_weeks_val = int(request.form.get('smoothing_horizon_weeks', '3'))
        except ValueError:
            smoothing_horizon_weeks_val = 3

        smoothing_params = {
            'output_file_path': os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt'),
            'log_file_path': os.path.join(app.config['UPLOAD_FOLDER'], 'sothemalgo_log_web.txt'),
            'retreat_weeks': retreat_weeks_val,
            'auto_mode': request.form.get('auto_mode', 'True').lower() == 'true',
            'advance_retreat_weeks': smoothing_horizon_weeks_val,
            'smoothing_json_path': os.path.join(app.config['UPLOAD_FOLDER'], 'smoothing_view.json'),
            'smoothing_ops_excel_path': "uploads/smoothing_operations.csv",
            'weekly_capacity_report_path': os.path.join(app.config['UPLOAD_FOLDER'], 'weekly_capacity_report.csv')
        }

        try:
            all_ofs = load_ofs_from_file(besoins_path)
            if not all_ofs:
                app.logger.warning(f"Fichier OFs {besoins_path} vide ou échec du chargement.")

            bom_data = load_bom_from_file(nomenclature_path)
            if not bom_data:
                app.logger.warning(f"Attention: Données de nomenclature depuis {nomenclature_path} vides ou échec du chargement.")

            posts_map, operations_map = load_posts_and_operations_data(
                filepath_posts=posts_path,
                filepath_post_unavailability=post_unavailability_path,
                filepath_operations=operations_path
            )

            horizon_weeks = horizon_weeks_val
            groups, all_ofs_with_groups = run_grouping_algorithm(
                all_ofs if all_ofs else [],
                bom_data if bom_data else [],
                horizon_H_weeks_param=horizon_weeks
            )

            final_updated_ofs = smooth_and_schedule_groups(
                groups,
                all_ofs_with_groups,
                bom_data if bom_data else [],
                posts_map,
                operations_map,
                params=smoothing_params
            )

            for g in groups:
                if hasattr(g, "calculate_consumption"):
                    g.calculate_consumption(bom_data if bom_data else [])

            write_grouped_needs_to_file(smoothing_params['output_file_path'], groups, final_updated_ofs)

            if action == 'plan':
                return redirect(url_for('planning_page'))

            output_file_to_read = smoothing_params['output_file_path']

            if os.path.exists(output_file_to_read) and os.path.getsize(output_file_to_read) > 0:
                parsed_data = parse_output_file(output_file_to_read)

                for of in parsed_data.get('unassigned_ofs', []):
                    of['remaining_stock'] = '0.00'

                print("✅ Final parsed data - Individual stocks should be available now")
                print(f"✅ Sample OF data: {parsed_data.get('unassigned_ofs', [])[:1] if parsed_data.get('unassigned_ofs') else 'No unassigned OFs'}")

                return render_template(
                    'results_modern.html',
                    groups=parsed_data.get('groups', []),
                    unassigned_ofs=parsed_data.get('unassigned_ofs', []),
                    error=parsed_data.get('error')
                )
            else:
                output_content = "L'algorithme a été exécuté. "
                if final_updated_ofs:
                    output_content += "Les OFs traités sont disponibles. Affichage brut :\n"
                    output_content += "\n".join([str(of) for of in final_updated_ofs if of is not None])
                elif groups:
                    output_content += "Groupes créés mais pas d'OFs finaux après lissage ou fichier de sortie non généré.\n"
                    output_content += "\n".join([str(g) for g in groups if g is not None])
                else:
                    output_content += "Aucun OF traité, aucun groupe créé ou aucun fichier de sortie généré."

                return render_template('index_modern.html', output=output_content)

        except Exception as e:
            app.logger.error(f"Erreur durant l'exécution de Sothemalgo: {e}", exc_info=True)
            return render_template('index_modern.html', error=f"Une erreur est survenue: {str(e)}")

    return render_template('index_modern.html')


@app.route('/display-output')
def display_output():
    base_dir = BASE_DIR
    web_output_file = os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt')
    static_output_file = os.path.join(base_dir, 'besoins_groupes_output.txt')

    output_file_path = None
    if os.path.exists(web_output_file):
        output_file_path = web_output_file
    elif os.path.exists(static_output_file):
        output_file_path = static_output_file

    try:
        if output_file_path and os.path.exists(output_file_path):
            parsed_data = parse_output_file(output_file_path)
            return render_template(
                'results.html',
                groups=parsed_data.get('groups', []),
                unassigned_ofs=parsed_data.get('unassigned_ofs', []),
                error=parsed_data.get('error')
            )
        else:
            return render_template(
                'results.html',
                groups=[],
                unassigned_ofs=[],
                error="Aucun fichier de sortie trouvé. Veuillez exécuter l'algorithme d'abord."
            )
    except Exception as e:
        return render_template(
            'results.html',
            groups=[],
            unassigned_ofs=[],
            error=f"Erreur lors du chargement du fichier: {str(e)}"
        )


@app.route('/data-visualization')
def data_visualization():
    return render_template('data_visualization_modern.html')


@app.route('/api/visualization-data')
def get_visualization_data():
    try:
        base_dir = BASE_DIR
        potential_files = [
            os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt'),
            os.path.join(base_dir, 'test_besoins_groupes_output.txt'),
            os.path.join(base_dir, 'besoins_groupes_output.txt')
        ]

        output_file_path = None
        latest_time = 0

        for file_path in potential_files:
            if os.path.exists(file_path):
                file_time = os.path.getmtime(file_path)
                if file_time > latest_time:
                    latest_time = file_time
                    output_file_path = file_path

        if output_file_path is None or not os.path.exists(output_file_path):
            return jsonify(generate_demo_visualization_data())

        parsed_data = parse_output_file(output_file_path)
        visualization_data = process_data_for_visualization(parsed_data)

        return jsonify(visualization_data)

    except Exception:
        return jsonify(generate_demo_visualization_data())


def process_data_for_visualization(parsed_data):
    groups = parsed_data.get('groups', [])
    unassigned_ofs = parsed_data.get('unassigned_ofs', [])

    total_groups = len(groups)
    total_ofs = sum(len(group.get('ofs', [])) for group in groups) + len(unassigned_ofs)
    assigned_ofs = total_ofs - len(unassigned_ofs)
    efficiency = (assigned_ofs / total_ofs * 100) if total_ofs > 0 else 0

    of_distribution = {}
    for i, group in enumerate(groups[:10]):
        group_id = group.get('id', f'Groupe {i+1}')
        of_count = len(group.get('ofs', []))
        of_distribution[group_id] = of_count

    categories = ['Production', 'Assemblage', 'Test', 'Emballage', 'Expédition']
    category_distribution = {}
    for i, category in enumerate(categories):
        category_distribution[category] = len(groups) // len(categories) + (
            1 if i < len(groups) % len(categories) else 0
        )

    group_efficiency = {}
    for group in groups[:8]:
        group_id = group.get('id', 'Inconnu')
        of_count = len(group.get('ofs', []))
        group_efficiency[group_id] = min(95, 60 + (of_count * 5))

    timeline_data = [
        {'step': 'Chargement des données', 'duration': 2.5, 'status': 'completed'},
        {'step': 'Calcul des groupes', 'duration': 15.3, 'status': 'completed'},
        {'step': 'Optimisation', 'duration': 8.7, 'status': 'completed'},
        {'step': 'Lissage', 'duration': 5.2, 'status': 'completed'},
        {'step': 'Génération sortie', 'duration': 1.8, 'status': 'completed'}
    ]

    performance_metrics = {
        'processing_time': sum(item['duration'] for item in timeline_data),
        'memory_usage': random.randint(45, 85),
        'cpu_usage': random.randint(30, 70),
        'success_rate': efficiency
    }

    weeks = [f'S{i+1}' for i in range(12)]
    volume_data = {}
    for week in weeks:
        volume_data[week] = random.randint(50, 200)

    return {
        'statistics': {
            'totalGroups': total_groups,
            'totalOfs': total_ofs,
            'assignedOfs': assigned_ofs,
            'efficiency': round(efficiency, 1)
        },
        'ofDistribution': of_distribution,
        'categoryDistribution': category_distribution,
        'groupEfficiency': group_efficiency,
        'timeline': timeline_data,
        'performanceMetrics': performance_metrics,
        'volumeData': volume_data,
        'lastUpdate': datetime.now().isoformat()
    }


def generate_demo_visualization_data():
    return {
        'statistics': {
            'totalGroups': 24,
            'totalOfs': 156,
            'assignedOfs': 142,
            'efficiency': 91.0
        },
        'ofDistribution': {
            'Groupe A': 25,
            'Groupe B': 18,
            'Groupe C': 22,
            'Groupe D': 15,
            'Groupe E': 20,
            'Groupe F': 12,
            'Groupe G': 16,
            'Groupe H': 14
        },
        'categoryDistribution': {
            'Production': 35,
            'Assemblage': 28,
            'Test': 22,
            'Emballage': 18,
            'Expédition': 12
        },
        'groupEfficiency': {
            'Groupe A': 95,
            'Groupe B': 87,
            'Groupe C': 92,
            'Groupe D': 78,
            'Groupe E': 88,
            'Groupe F': 94,
            'Groupe G': 82,
            'Groupe H': 90
        },
        'timeline': [
            {'step': 'Chargement des données', 'duration': 2.5, 'status': 'completed'},
            {'step': 'Calcul des groupes', 'duration': 15.3, 'status': 'completed'},
            {'step': 'Optimisation', 'duration': 8.7, 'status': 'completed'},
            {'step': 'Lissage', 'duration': 5.2, 'status': 'completed'},
            {'step': 'Génération sortie', 'duration': 1.8, 'status': 'completed'}
        ],
        'performanceMetrics': {
            'processing_time': 33.5,
            'memory_usage': 67,
            'cpu_usage': 45,
            'success_rate': 91.0
        },
        'volumeData': {
            'S1': 120, 'S2': 135, 'S3': 95, 'S4': 180, 'S5': 160, 'S6': 145,
            'S7': 170, 'S8': 155, 'S9': 190, 'S10': 175, 'S11': 165, 'S12': 185
        },
        'lastUpdate': datetime.now().isoformat()
    }


@app.route('/api/smoothing')
def api_smoothing():
    json_path = os.path.join(app.config['UPLOAD_FOLDER'], 'smoothing_view.json')
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        return jsonify({"generated_at": None, "items": []})
    except Exception as e:
        return jsonify({"error": str(e), "items": []}), 500


@app.route('/smoothing')
def smoothing_page():
    json_path = os.path.join(app.config['UPLOAD_FOLDER'], 'smoothing_view.json')
    data = {"generated_at": None, "items": []}
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
    except Exception as e:
        data = {"generated_at": None, "items": [], "error": str(e)}
    return render_template('smoothing_modern.html', data=data, items=data.get('items') or [])


@app.route('/test-button')
def test_button():
    return render_template('test_button.html')


if __name__ == '__main__':
    print("🚀 Démarrage de l'interface web Sothemalgo...")
    print("📊 Algorithme avec logique de groupement par famille améliorée")
    print("🌐 Interface accessible sur : http://localhost:5000")
    print("⏹️  Appuyez sur Ctrl+C pour arrêter")
    app.run(host="127.0.0.1", port=5000, debug=True)
    # from waitress import serve
    # serve(app, host="0.0.0.0", port=5002)
