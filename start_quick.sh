#!/bin/bash

# 🚀 Script de Démarrage Rapide - Sothemalgo v2.0
# Ce script permet de démarrer rapidement le projet après nettoyage

echo "🚀 Sothemalgo v2.0 - Démarrage Rapide"
echo "===================================="
echo ""

# Vérification de l'environnement
echo "🔍 Vérification de l'environnement..."

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n'est pas installé"
    exit 1
fi

python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python $python_version détecté"

# Vérifier si l'environnement virtuel existe
if [[ -d "sothemalgo_env" ]]; then
    echo "✅ Environnement virtuel détecté"
    
    # Activer l'environnement virtuel
    if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        source sothemalgo_env/Scripts/activate
    else
        source sothemalgo_env/bin/activate
    fi
    
    echo "✅ Environnement virtuel activé"
else
    echo "⚠️  Environnement virtuel non trouvé"
    echo "   Création d'un nouvel environnement..."
    
    python3 -m venv sothemalgo_env
    
    if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        source sothemalgo_env/Scripts/activate
    else
        source sothemalgo_env/bin/activate
    fi
    
    pip install -r requirements.txt
    echo "✅ Environnement virtuel créé et configuré"
fi

echo ""
echo "📋 MENU - Que souhaitez-vous faire ?"
echo "=================================="
echo "1. 🧪 Tester l'algorithme"
echo "2. 🌐 Lancer l'interface web"
echo "3. 🔍 Vérifier le projet"
echo "4. 📖 Voir la documentation"
echo "5. 📊 Voir les fichiers de test"
echo "6. 📦 Voir les options d'installation des dépendances"
echo "7. 🧪 Tester les dépendances installées"
echo "0. ❌ Quitter"
echo ""

read -p "Votre choix (0-7): " choice

case $choice in
    1)
        echo ""
        echo "🧪 Test de l'algorithme en cours..."
        python3 test_new_algo.py
        echo ""
        echo "✅ Test terminé ! Vérifiez le fichier test_besoins_groupes_output_new.txt"
        ;;
    2)
        echo ""
        echo "🌐 Démarrage de l'interface web..."
        echo "   URL: http://localhost:5002"
        echo "   Appuyez sur Ctrl+C pour arrêter"
        echo ""
        python3 sothemalgo_web.py
        ;;
    3)
        echo ""
        echo "🔍 Vérification du projet..."
        ./verify_project.sh
        ;;
    4)
        echo ""
        echo "📖 Documentation disponible:"
        echo "   - README.md (documentation complète)"
        echo "   - CLEANUP_REPORT.md (rapport de nettoyage)"
        echo ""
        if command -v cat &> /dev/null; then
            echo "Aperçu du README.md:"
            echo "==================="
            head -20 README.md
            echo "..."
            echo "(Ouvrez README.md pour voir la documentation complète)"
        fi
        ;;
    5)
        echo ""
        echo "📊 Fichiers de test disponibles:"
        echo "   - test_besoins.csv (besoins)"
        echo "   - test_nomenclature.csv (nomenclature)"
        echo "   - test_operations.csv (opérations)"
        echo "   - test_posts.csv (postes)"
        echo "   - test_post_unavailability.csv (indisponibilités)"
        echo ""
        echo "Fichiers clients (pour l'interface web):"
        echo "   - test_*_client.csv"
        ;;
    6)
        echo ""
        echo "📦 Options d'installation des dépendances:"
        ./show_dependencies.sh
        ;;
    7)
        echo ""
        echo "🧪 Test des dépendances installées..."
        python3 test_dependencies.py
        ;;
    0)
        echo ""
        echo "👋 Au revoir !"
        ;;
    *)
        echo ""
        echo "❌ Choix invalide"
        ;;
esac

echo ""
echo "🎯 AIDE RAPIDE:"
echo "==============="
echo "• Pour tester : python3 test_new_algo.py"
echo "• Pour l'interface web : python3 sothemalgo_web.py"
echo "• Pour vérifier : ./verify_project.sh"
echo "• Documentation : README.md"
echo ""
echo "🔗 Projet nettoyé et optimisé !"
