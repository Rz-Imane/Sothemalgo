#!/bin/bash

# Script d'information sur les dépendances Sothemalgo
# Affiche les options d'installation disponibles

echo "📦 Options d'installation des dépendances Sothemalgo"
echo "=================================================="
echo ""

echo "📋 OPTION 1 : Installation complète (recommandée)"
echo "   Fichier : requirements.txt"
echo "   Contenu :"
if [[ -f "requirements.txt" ]]; then
    cat requirements.txt | sed 's/^/     /'
else
    echo "     ❌ Fichier requirements.txt non trouvé"
fi

echo ""
echo "📋 OPTION 2 : Installation minimale (plus rapide)"
echo "   Fichier : requirements-minimal.txt"
echo "   Contenu :"
if [[ -f "requirements-minimal.txt" ]]; then
    cat requirements-minimal.txt | sed 's/^/     /'
else
    echo "     ❌ Fichier requirements-minimal.txt non trouvé"
fi

echo ""
echo "🚀 COMMANDES D'INSTALLATION"
echo "============================"
echo ""
echo "Unix/Linux/Mac :"
echo "   source sothemalgo_env/bin/activate"
echo "   pip install -r requirements.txt          # Installation complète"
echo "   pip install -r requirements-minimal.txt  # Installation minimale"
echo ""
echo "Windows :"
echo "   sothemalgo_env\\Scripts\\activate"
echo "   pip install -r requirements.txt          # Installation complète"
echo "   pip install -r requirements-minimal.txt  # Installation minimale"
echo ""

echo "💡 RECOMMANDATIONS"
echo "=================="
echo "✅ Pour la production     : requirements.txt (toutes les versions)"
echo "✅ Pour le développement  : requirements.txt (stabilité)"
echo "✅ Pour un test rapide    : requirements-minimal.txt (minimum viable)"
echo "✅ Pour un environnement contraint : requirements-minimal.txt"
echo ""

echo "🔍 VÉRIFICATION"
echo "==============="
echo "Après installation, vérifiez avec :"
echo "   python -c \"import flask, pandas, numpy; print('✅ Dépendances OK')\""
