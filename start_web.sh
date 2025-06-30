#!/usr/bin/env zsh

# 🏭 Sothemalgo Web Server - Script de démarrage optimisé
# Auteur: Sothemalgo Team
# Version: 2.0
# Usage: ./start_web.sh [port]

set -e  # Arrêter le script en cas d'erreur

# Configuration
DEFAULT_PORT=5002
PORT=${1:-$DEFAULT_PORT}
PROJECT_NAME="Sothemalgo"
VENV_DIR="sothemalgo_env"
REQUIRED_FILES=("sothemalgo_web.py" "sothemalgo_grouper.py" "templates/index.html")

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Fonctions utilitaires
print_header() {
    echo "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo "${BLUE}🏭 ${PROJECT_NAME} Web Interface v2.0${NC}"
    echo "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo "${RED}❌ $1${NC}"
    exit 1
}

print_info() {
    echo "${BLUE}ℹ️  $1${NC}"
}

# Se placer dans le répertoire du script
cd "$(dirname "$0")"

print_header

# Vérifications préliminaires
print_info "Vérification de l'environnement..."

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 n'est pas installé!"
fi

# Vérifier les fichiers requis
for file in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        print_error "Fichier manquant: $file"
    fi
done

print_success "Environnement vérifié"

# Gestion de l'environnement virtuel
if [[ ! -d "$VENV_DIR" ]]; then
    print_info "Création de l'environnement virtuel..."
    python3 -m venv $VENV_DIR
    
    print_info "Installation des dépendances..."
    source $VENV_DIR/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet flask pandas numpy
    print_success "Environnement virtuel créé et configuré"
else
    print_info "Activation de l'environnement virtuel..."
    source $VENV_DIR/bin/activate
    print_success "Environnement virtuel activé"
fi

# Créer les dossiers nécessaires
mkdir -p uploads
mkdir -p logs

# Vérifier si le port est disponible
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    print_warning "Le port $PORT est déjà utilisé"
    print_info "Tentative d'arrêt du processus existant..."
    pkill -f "python.*sothemalgo_web.py" || true
    sleep 2
fi

# Information de démarrage
print_success "Configuration terminée"
echo ""
print_info "🌐 Serveur web: http://127.0.0.1:$PORT"
print_info "📊 Visualisation: http://127.0.0.1:$PORT/data-visualization"
print_info "🔧 API: http://127.0.0.1:$PORT/api/visualization-data"
echo ""
print_warning "Appuyez sur Ctrl+C pour arrêter le serveur"
echo ""

# Lancer l'application
print_info "Démarrage du serveur Sothemalgo..."
export FLASK_ENV=development
export FLASK_DEBUG=0
python sothemalgo_web.py
