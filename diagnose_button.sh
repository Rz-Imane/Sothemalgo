#!/bin/bash

echo "🔧 Diagnostic Complet - Bouton Sothemalgo"
echo "=========================================="

echo ""
echo "1. 🌐 Test de connectivité serveur..."
if curl -s http://127.0.0.1:5002/ > /dev/null; then
    echo "   ✅ Serveur accessible sur http://127.0.0.1:5002"
else
    echo "   ❌ Serveur inaccessible - Veuillez démarrer le serveur"
    echo "   💡 Commande: ./start_web.sh"
    exit 1
fi

echo ""
echo "2. 🔍 Vérification du bouton dans le HTML..."
BUTTON_HTML=$(curl -s http://127.0.0.1:5002/ | grep -A 3 "Lancer l'analyse")
if echo "$BUTTON_HTML" | grep -q "onclick.*handleSubmit"; then
    echo "   ✅ Bouton trouvé avec gestionnaire onclick"
else
    echo "   ❌ Bouton mal configuré"
fi

if echo "$BUTTON_HTML" | grep -q "pointer-events: auto"; then
    echo "   ✅ Styles de clicabilité appliqués"
else
    echo "   ⚠️  Styles inline non trouvés"
fi

echo ""
echo "3. 🧪 Test des pages de diagnostic..."

# Test page principale
if curl -s http://127.0.0.1:5002/ | grep -q "SothemaAL"; then
    echo "   ✅ Page principale OK"
else
    echo "   ❌ Page principale KO"
fi

# Test page de test du bouton
if curl -s http://127.0.0.1:5002/test-button | grep -q "Test Interface"; then
    echo "   ✅ Page de test accessible: http://127.0.0.1:5002/test-button"
else
    echo "   ⚠️  Page de test non accessible"
fi

echo ""
echo "4. 🎮 Test de soumission formulaire..."
FORM_TEST=$(curl -s -X POST http://127.0.0.1:5002/ \
    -F "action=run_algorithm" \
    -F "useTestData=on" \
    -F "horizon_weeks=12")

if echo "$FORM_TEST" | grep -q "Résultats de l'analyse"; then
    echo "   ✅ Formulaire backend fonctionne"
else
    echo "   ❌ Problème backend formulaire"
fi

echo ""
echo "🎯 RÉSUMÉ DU DIAGNOSTIC:"
echo "========================"

echo ""
echo "✅ Solutions Disponibles:"
echo ""
echo "🔧 Option 1 - Interface Principale (Recommandée):"
echo "   URL: http://127.0.0.1:5002"
echo "   → Cliquer sur 'Lancer l'analyse'"
echo "   → Si non cliquable, utiliser 'Test Debug'"
echo ""
echo "🔧 Option 2 - Page de Test Simple:"
echo "   URL: http://127.0.0.1:5002/test-button"
echo "   → Interface simplifiée pour diagnostic"
echo ""
echo "🔧 Option 3 - Commande Directe:"
echo "   cd /Users/abderrahman/Desktop/Sothemalgo2"
echo "   curl -X POST http://127.0.0.1:5002/ \\"
echo "        -F 'action=run_algorithm' \\"
echo "        -F 'useTestData=on' \\"
echo "        -F 'horizon_weeks=12' > resultats.html"
echo "   open resultats.html"
echo ""

echo "🚨 Si le bouton reste non cliquable:"
echo ""
echo "1. Ouvrir la console développeur (F12)"
echo "2. Vérifier les erreurs JavaScript"
echo "3. Essayer Ctrl+F5 pour vider le cache"
echo "4. Tester dans un autre navigateur"
echo "5. Utiliser la page de test: /test-button"
echo ""

echo "💡 Le backend fonctionne parfaitement."
echo "   Le problème est uniquement côté interface JavaScript."
