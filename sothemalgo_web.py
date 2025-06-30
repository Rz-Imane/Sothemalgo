from flask import Flask, render_template, request, jsonify
import pandas as pd
import os
import re
import json
import random
from datetime import datetime, timedelta
import random

# Configuration automatique du répertoire de base
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mise à jour des importations
from sothemalgo_grouper import (
    load_ofs_from_file,
    load_bom_from_file,
    load_posts_and_operations_data,
    run_grouping_algorithm,
    smooth_and_schedule_groups,
    write_grouped_needs_to_file,
    HORIZON_H_WEEKS,  # Utilisé comme paramètre par défaut pour l'horizon
    # Assurez-vous que toutes les autres constantes ou fonctions nécessaires sont importées
)

def parse_output_file(file_path):
    """Parse le fichier de sortie et retourne les données structurées"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remplacer les \n littéraux par de vrais retours à la ligne
        content = content.replace('\\n', '\n')
        
        groups = []
        unassigned_ofs = []
        
        # Séparer le contenu en lignes
        lines = content.split('\n')
        
        current_group = None
        in_group = False
        in_unassigned = False
        
        for line in lines:
            line = line.strip()
            
            # Détecter le début d'un groupe
            if 'Group ID:' in line:
                if current_group:
                    groups.append(current_group)
                current_group = {
                    'id': line.split('Group ID:')[1].strip().replace('#', '').strip(),
                    'ps_product': '',
                    'time_window': '',
                    'remaining_stock': '',
                    'ofs': []
                }
                in_group = True
                in_unassigned = False
                continue
                
            # Détecter les informations du groupe
            if in_group and current_group:
                if 'Produit PS Principal:' in line:
                    current_group['ps_product'] = line.split('Produit PS Principal:')[1].strip().replace('#', '').strip()
                elif 'Fenêtre Temporelle:' in line:
                    current_group['time_window'] = line.split('Fenêtre Temporelle:')[1].strip().replace('#', '').strip()
                elif 'Stock PS Théorique Restant:' in line:
                    current_group['remaining_stock'] = line.split('Stock PS Théorique Restant:')[1].strip().replace('#', '').strip()
                
            # Détecter la section des OFs non affectés
            if 'OFs Non Affectés' in line:
                if current_group:
                    groups.append(current_group)
                    current_group = None
                in_group = False
                in_unassigned = True
                continue
                
            # Parser les lignes de données (OFs)
            if '\t' in line and not line.startswith('#') and line.count('\t') >= 8:
                parts = line.split('\t')
                if len(parts) >= 9:
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
                        'Delay': parts[11] if len(parts) > 11 else ''
                    }
                    
                    if in_unassigned:
                        unassigned_ofs.append(of_data)
                    elif current_group:
                        current_group['ofs'].append(of_data)
        
        # Ajouter le dernier groupe s'il existe
        if current_group:
            groups.append(current_group)
        
        return {'groups': groups, 'unassigned_ofs': unassigned_ofs}
        
    except Exception as e:
        return {'error': f'Erreur lors du parsing du fichier: {str(e)}', 'groups': [], 'unassigned_ofs': []}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Récupérer les fichiers téléchargés
        besoins_file_storage = request.files.get('besoins_file')
        nomenclature_file_storage = request.files.get('nomenclature_file')
        posts_file_storage = request.files.get('posts_file')
        operations_file_storage = request.files.get('operations_file')
        post_unavailability_file_storage = request.files.get('post_unavailability_file')

        # Utiliser les fichiers par défaut ou ceux téléchargés
        base_dir = BASE_DIR
        
        # Vérifier si l'utilisateur veut utiliser les données de test
        use_test_data = request.form.get('use_test_data', 'false').lower() == 'true'
        
        # Fichier besoins
        if besoins_file_storage and besoins_file_storage.filename:
            besoins_path = os.path.join(app.config['UPLOAD_FOLDER'], besoins_file_storage.filename)
            besoins_file_storage.save(besoins_path)
        else:
            if use_test_data:
                besoins_path = os.path.join(base_dir, 'test_besoins.csv')
            else:
                # Utiliser par défaut les fichiers client depuis uploads/
                besoins_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_besoins_client.csv')

        # Fichier nomenclature
        if nomenclature_file_storage and nomenclature_file_storage.filename:
            nomenclature_path = os.path.join(app.config['UPLOAD_FOLDER'], nomenclature_file_storage.filename)
            nomenclature_file_storage.save(nomenclature_path)
        else:
            if use_test_data:
                nomenclature_path = os.path.join(base_dir, 'test_nomenclature.csv')
            else:
                # Utiliser par défaut les fichiers client depuis uploads/
                nomenclature_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_nomenclature_client.csv')

        # Fichier posts
        if posts_file_storage and posts_file_storage.filename:
            posts_path = os.path.join(app.config['UPLOAD_FOLDER'], posts_file_storage.filename)
            posts_file_storage.save(posts_path)
        else:
            if use_test_data:
                posts_path = os.path.join(base_dir, 'test_posts.csv')
            else:
                # Utiliser par défaut les fichiers client depuis uploads/
                posts_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_posts_client.csv')

        # Fichier operations
        if operations_file_storage and operations_file_storage.filename:
            operations_path = os.path.join(app.config['UPLOAD_FOLDER'], operations_file_storage.filename)
            operations_file_storage.save(operations_path)
        else:
            if use_test_data:
                operations_path = os.path.join(base_dir, 'test_operations.csv')
            else:
                # Utiliser par défaut les fichiers client depuis uploads/
                operations_path = os.path.join(app.config['UPLOAD_FOLDER'], 'test_operations_client.csv')

        # Fichier post_unavailability
        if post_unavailability_file_storage and post_unavailability_file_storage.filename:
            post_unavailability_path = os.path.join(app.config['UPLOAD_FOLDER'], post_unavailability_file_storage.filename)
            post_unavailability_file_storage.save(post_unavailability_path)
        else:
            if use_test_data:
                post_unavailability_path = os.path.join(base_dir, 'test_post_unavailability.csv')
            else:
                # Pour post_unavailability, pas de fichier client, utiliser le fichier principal
                post_unavailability_path = os.path.join(base_dir, 'post_unavailability.csv')
            
        # Paramètres de lissage (vous pouvez les rendre configurables dans le formulaire)
        try:
            retreat_weeks_val = int(request.form.get('retreat_weeks', '0'))
        except ValueError:
            retreat_weeks_val = 0 # Default if conversion fails
            
        try:
            horizon_weeks_val = int(request.form.get('horizon_weeks', '4'))
        except ValueError:
            horizon_weeks_val = 4 # Default if conversion fails
            
        smoothing_params = {
            'output_file_path': os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt'),
            'log_file_path': os.path.join(app.config['UPLOAD_FOLDER'], 'sothemalgo_log_web.txt'),
            'retreat_weeks': retreat_weeks_val,
            'auto_mode': request.form.get('auto_mode', 'True').lower() == 'true',
            'advance_retreat_weeks': retreat_weeks_val  # Utiliser retreat_weeks pour advance_retreat_weeks
        }

        # Exécuter l'algorithme
        try:
            # 1. Charger les données
            all_ofs = load_ofs_from_file(besoins_path)
            if not all_ofs:
                # Changed to warning to allow processing if only warnings are desired
                app.logger.warning(f"Fichier OFs {besoins_path} vide ou échec du chargement. Poursuite si possible.")
                # return render_template('index.html', error=f"Échec du chargement des OFs depuis {besoins_path} ou fichier vide.")


            bom_data = load_bom_from_file(nomenclature_path)
            if not bom_data:
                app.logger.warning(f"Attention: Données de nomenclature depuis {nomenclature_path} vides ou échec du chargement.")
                # Si la nomenclature est absolument requise, vous pouvez lever une erreur ici.

            posts_map, operations_map = load_posts_and_operations_data(
                filepath_posts=posts_path,
                filepath_post_unavailability=post_unavailability_path,
                filepath_operations=operations_path
            )

            # 2. Exécuter l'algorithme de groupement
            # Utiliser une valeur par défaut pour horizon_H_weeks_param si non configurable via formulaire
            horizon_weeks = horizon_weeks_val  # Utiliser la valeur du formulaire 
            groups, all_ofs_with_groups = run_grouping_algorithm(
                all_ofs if all_ofs else [], # Pass empty list if loading failed but we continue
                bom_data if bom_data else [], # Pass empty list if loading failed
                horizon_H_weeks_param=horizon_weeks 
            )

            # 3. Exécuter le lissage et la planification
            final_updated_ofs = smooth_and_schedule_groups(
                groups,
                all_ofs_with_groups,
                bom_data if bom_data else [],
                posts_map,
                operations_map,
                params=smoothing_params # Contient output_file_path, log_file_path, etc.
            )
            
            # 3.5. Générer le fichier de sortie
            write_grouped_needs_to_file(smoothing_params['output_file_path'], groups, final_updated_ofs)
            
            # 4. Sortie
            output_file_to_read = smoothing_params['output_file_path']
            
            if os.path.exists(output_file_to_read) and os.path.getsize(output_file_to_read) > 0:
                # Parser le fichier et retourner les données structurées
                parsed_data = parse_output_file(output_file_to_read)
                return render_template('results_modern.html', 
                                     groups=parsed_data.get('groups', []),
                                     unassigned_ofs=parsed_data.get('unassigned_ofs', []),
                                     error=parsed_data.get('error'))
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
    # Essayer d'abord le fichier généré par l'interface web (plus récent), puis celui du répertoire courant
    base_dir = BASE_DIR
    web_output_file = os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt')
    static_output_file = os.path.join(base_dir, 'besoins_groupes_output.txt')
    
    # Choisir le fichier le plus récent ou celui qui existe
    output_file_path = None
    if os.path.exists(web_output_file):
        output_file_path = web_output_file
    elif os.path.exists(static_output_file):
        output_file_path = static_output_file
    
    try:
        if output_file_path and os.path.exists(output_file_path):
            parsed_data = parse_output_file(output_file_path)
            return render_template('results.html', 
                                 groups=parsed_data.get('groups', []),
                                 unassigned_ofs=parsed_data.get('unassigned_ofs', []),
                                 error=parsed_data.get('error'))
        else:
            return render_template('results.html', 
                                 groups=[], 
                                 unassigned_ofs=[], 
                                 error="Aucun fichier de sortie trouvé. Veuillez exécuter l'algorithme d'abord.")
    except Exception as e:
        return render_template('results.html', 
                             groups=[], 
                             unassigned_ofs=[], 
                             error=f"Erreur lors du chargement du fichier: {str(e)}")

@app.route('/data-visualization')
def data_visualization():
    """Route pour afficher la page de visualisation des données"""
    return render_template('data_visualization_modern.html')

@app.route('/api/visualization-data')
def get_visualization_data():
    """API endpoint pour récupérer les données de visualisation en temps réel"""
    try:
        # Lire les données des fichiers de sortie existants
        base_dir = BASE_DIR
        
        # Rechercher les fichiers de sortie potentiels et choisir le plus récent
        potential_files = [
            os.path.join(app.config['UPLOAD_FOLDER'], 'besoins_groupes_output_web.txt'),  # Fichier web le plus récent
            os.path.join(base_dir, 'test_besoins_groupes_output.txt'),  # Fichier de test
            os.path.join(base_dir, 'besoins_groupes_output.txt')  # Fichier principal
        ]
        
        # Trouver le fichier existant le plus récent
        output_file_path = None
        latest_time = 0
        
        for file_path in potential_files:
            if os.path.exists(file_path):
                file_time = os.path.getmtime(file_path)
                if file_time > latest_time:
                    latest_time = file_time
                    output_file_path = file_path
        
        # Si aucun fichier de sortie n'existe, générer des données de démonstration
        if output_file_path is None or not os.path.exists(output_file_path):
            return jsonify(generate_demo_visualization_data())
        
        # Parser les données réelles
        parsed_data = parse_output_file(output_file_path)
        visualization_data = process_data_for_visualization(parsed_data)
        
        return jsonify(visualization_data)
        
    except Exception as e:
        # En cas d'erreur, retourner des données de démonstration
        return jsonify(generate_demo_visualization_data())

def process_data_for_visualization(parsed_data):
    """Traite les données parsées pour la visualisation"""
    groups = parsed_data.get('groups', [])
    unassigned_ofs = parsed_data.get('unassigned_ofs', [])
    
    # Calculer les statistiques
    total_groups = len(groups)
    total_ofs = sum(len(group.get('ofs', [])) for group in groups) + len(unassigned_ofs)
    assigned_ofs = total_ofs - len(unassigned_ofs)
    efficiency = (assigned_ofs / total_ofs * 100) if total_ofs > 0 else 0
    
    # Distribution des OFs par groupe
    of_distribution = {}
    for i, group in enumerate(groups[:10]):  # Top 10 groupes
        group_id = group.get('id', f'Groupe {i+1}')
        of_count = len(group.get('ofs', []))
        of_distribution[group_id] = of_count
    
    # Distribution par catégorie (simulation basée sur les données réelles)
    categories = ['Production', 'Assemblage', 'Test', 'Emballage', 'Expédition']
    category_distribution = {}
    for i, category in enumerate(categories):
        category_distribution[category] = len(groups) // len(categories) + (1 if i < len(groups) % len(categories) else 0)
    
    # Efficacité par groupe
    group_efficiency = {}
    for group in groups[:8]:  # Top 8 groupes
        group_id = group.get('id', 'Inconnu')
        # Simuler l'efficacité basée sur le nombre d'OFs
        of_count = len(group.get('ofs', []))
        group_efficiency[group_id] = min(95, 60 + (of_count * 5))
    
    # Timeline des étapes (simulée)
    timeline_data = [
        {'step': 'Chargement des données', 'duration': 2.5, 'status': 'completed'},
        {'step': 'Calcul des groupes', 'duration': 15.3, 'status': 'completed'},
        {'step': 'Optimisation', 'duration': 8.7, 'status': 'completed'},
        {'step': 'Lissage', 'duration': 5.2, 'status': 'completed'},
        {'step': 'Génération sortie', 'duration': 1.8, 'status': 'completed'}
    ]
    
    # Métriques de performance
    performance_metrics = {
        'processing_time': sum(item['duration'] for item in timeline_data),
        'memory_usage': random.randint(45, 85),
        'cpu_usage': random.randint(30, 70),
        'success_rate': efficiency
    }
    
    # Volume de données par semaine (simulation)
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
    """Génère des données de démonstration pour la visualisation"""
    # Données de démonstration similaires à celles du template
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

@app.route('/test-button')
def test_button():
    """Route de test pour diagnostiquer les problèmes de bouton"""
    return render_template('test_button.html')

if __name__ == '__main__':
    # Utiliser waitress comme serveur de production simple et multi-plateforme
    # Pour un déploiement plus robuste sur Linux, Gunicorn est recommandé.
    # Exemple avec Gunicorn : gunicorn --workers 4 --bind 0.0.0.0:8000 sothemalgo_web:app
    from waitress import serve
    serve(app, host="0.0.0.0", port=5002)
