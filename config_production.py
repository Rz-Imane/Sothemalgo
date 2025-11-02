# Configuration de production pour Sothemalgo
import os

class ProductionConfig:
    """Configuration pour l'environnement de production"""
    
    # Sécurité
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
    
    # Flask
    DEBUG = False
    TESTING = False
    
    # Uploads
    UPLOAD_FOLDER = '/opt/sothemalgo/uploads'
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max
    
    # Logs
    LOG_LEVEL = 'INFO'
    LOG_FILE = '/opt/sothemalgo/logs/app.log'
    
    # Base de données (si vous en ajoutez une plus tard)
    # DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///sothemalgo.db')
    
    # Performance
    SEND_FILE_MAX_AGE_DEFAULT = 31536000  # 1 an pour les fichiers statiques

# Variables d'environnement recommandées
RECOMMENDED_ENV_VARS = {
    'FLASK_ENV': 'production',
    'FLASK_APP': 'sothemalgo_web.py',
    'SECRET_KEY': 'generate-a-strong-secret-key',
    'PYTHONPATH': '/opt/sothemalgo'
}
