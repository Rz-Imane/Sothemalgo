# 🏭 Configuration Sothemalgo Web Interface v2.0

# Paramètres du serveur Flask
FLASK_CONFIG = {
    'HOST': "127.0.0.1",
    'PORT': 5002,
    'DEBUG': False,
    'SECRET_KEY': 'sothemalgo-secure-key-2025'
}

# Chemins des fichiers par défaut (données de production)
DEFAULT_FILES = {
    'besoins': 'besoins_non_lisse_x3.csv',
    'nomenclature': 'nomenclature_multi_niveaux.csv',
    'posts': 'posts.csv',
    'operations': 'operations.csv',
    'post_unavailability': 'post_unavailability.csv'
}

# Fichiers de test (données d'exemple)
TEST_FILES = {
    'besoins': 'test_besoins.csv',
    'nomenclature': 'test_nomenclature.csv',
    'posts': 'test_posts.csv',
    'operations': 'test_operations.csv',
    'post_unavailability': 'test_post_unavailability.csv'
}

# Paramètres de l'algorithme par défaut
ALGORITHM_DEFAULTS = {
    'retreat_weeks': 0,
    'auto_mode': True,
    'horizon_weeks': 4,
    'advance_retreat_weeks': 3
}

# Configuration des uploads
UPLOAD_CONFIG = {
    'FOLDER': 'uploads',
    'ALLOWED_EXTENSIONS': {'csv', 'txt'},
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,  # 16MB max
    'TIMEOUT': 300  # 5 minutes timeout
}

# Noms des fichiers de sortie
OUTPUT_FILES = {
    'web_output': 'besoins_groupes_output_web.txt',
    'log_file': 'sothemalgo_log_web.txt',
    'backup_folder': 'backups'
}

# Configuration de la visualisation
VISUALIZATION_CONFIG = {
    'refresh_interval': 5000,  # ms
    'chart_colors': [
        '#667eea', '#764ba2', '#f093fb', '#f5576c',
        '#4facfe', '#00f2fe', '#43e97b', '#38f9d7'
    ],
    'max_groups_display': 20,
    'performance_thresholds': {
        'excellent': 90,
        'good': 75,
        'warning': 60,
        'critical': 40
    }
}

# Messages de l'interface
UI_MESSAGES = {
    'success': {
        'algorithm_complete': "✅ Algorithme exécuté avec succès",
        'files_uploaded': "✅ Fichiers uploadés correctement",
        'data_processed': "✅ Données traitées"
    },
    'error': {
        'file_not_found': "❌ Fichier non trouvé",
        'invalid_format': "❌ Format de fichier invalide",
        'processing_error': "❌ Erreur lors du traitement"
    },
    'info': {
        'using_defaults': "ℹ️ Utilisation des fichiers par défaut",
        'processing': "⏳ Traitement en cours...",
        'loading': "📂 Chargement des données..."
    }
}

# Interface utilisateur
UI_CONFIG = {
    'app_title': 'Sothemalgo - Interface Web',
    'app_description': 'Algorithme de groupement et planification des ordres de fabrication',
    'max_results_per_page': 1000,
    'enable_drag_drop': True
}
