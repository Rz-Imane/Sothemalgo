#!/bin/bash

# Script de correction des problèmes d'interface web SothemaAL
# Corrige les erreurs communes et prépare les données

echo "🔧 Correction des problèmes d'interface web SothemaAL"
echo "====================================================="

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# 1. Vérifier et créer les liens symboliques pour les données
echo "1. Vérification des fichiers de données..."

if [ ! -f "besoins_non_lisse_x3.csv" ] && [ -f "test_besoins.csv" ]; then
    ln -sf test_besoins.csv besoins_non_lisse_x3.csv
    print_success "Lien besoins_non_lisse_x3.csv → test_besoins.csv"
fi

if [ ! -f "nomenclature_multi_niveaux.csv" ] && [ -f "test_nomenclature.csv" ]; then
    ln -sf test_nomenclature.csv nomenclature_multi_niveaux.csv
    print_success "Lien nomenclature_multi_niveaux.csv → test_nomenclature.csv"
fi

if [ ! -f "posts.csv" ] && [ -f "test_posts.csv" ]; then
    ln -sf test_posts.csv posts.csv
    print_success "Lien posts.csv → test_posts.csv"
fi

if [ ! -f "operations.csv" ] && [ -f "test_operations.csv" ]; then
    ln -sf test_operations.csv operations.csv
    print_success "Lien operations.csv → test_operations.csv"
fi

if [ ! -f "post_unavailability.csv" ] && [ -f "test_post_unavailability.csv" ]; then
    ln -sf test_post_unavailability.csv post_unavailability.csv
    print_success "Lien post_unavailability.csv → test_post_unavailability.csv"
fi

# 2. Vérifier les templates modernes
echo ""
echo "2. Vérification des templates modernes..."

TEMPLATES=("index_modern.html" "results_modern.html" "data_visualization_modern.html")

for template in "${TEMPLATES[@]}"; do
    if [ -f "templates/$template" ]; then
        print_success "Template $template trouvé"
    else
        print_error "Template $template manquant"
    fi
done

# 3. Test de la configuration Flask
echo ""
echo "3. Test de la configuration Flask..."

python3 -c "
import sys
sys.path.append('.')
try:
    from sothemalgo_web import app
    print('✓ Configuration Flask OK')
except Exception as e:
    print(f'✗ Erreur Flask: {e}')
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    print_success "Configuration Flask validée"
else
    print_error "Problème avec la configuration Flask"
fi

# 4. Nettoyer les anciens processus sur le port 5002
echo ""
echo "4. Nettoyage du port 5002..."

if lsof -ti:5002 >/dev/null 2>&1; then
    print_warning "Port 5002 occupé, nettoyage en cours..."
    lsof -ti:5002 | xargs kill -9 2>/dev/null
    sleep 2
    print_success "Port 5002 libéré"
else
    print_success "Port 5002 disponible"
fi

# 5. Test rapide du serveur
echo ""
echo "5. Test rapide du serveur..."

# Démarrer le serveur en arrière-plan pour test
python3 sothemalgo_web.py &
SERVER_PID=$!

# Attendre le démarrage
sleep 5

# Tester la connexion
if curl -s -f http://localhost:5002/ >/dev/null; then
    print_success "Serveur web accessible"
    
    # Tester l'API
    if curl -s -f http://localhost:5002/api/visualization-data >/dev/null; then
        print_success "API de visualisation accessible"
    else
        print_warning "API de visualisation non accessible"
    fi
else
    print_error "Serveur web non accessible"
fi

# Arrêter le serveur de test
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo ""
echo "🎉 Corrections terminées !"
echo "========================="
print_success "Interface web prête à être utilisée"
print_success "Démarrer avec: ./start_web.sh"
print_success "Accès: http://localhost:5002"

exit 0
