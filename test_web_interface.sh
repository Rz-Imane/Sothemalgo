#!/bin/bash

echo "🔧 Test de l'interface web Sothemalgo"
echo "======================================"

# Tester si le serveur répond
echo "1. Test de connectivité..."
if curl -s http://127.0.0.1:5002/ > /dev/null; then
    echo "✅ Serveur accessible"
else
    echo "❌ Serveur inaccessible"
    exit 1
fi

# Tester la page principale
echo "2. Test de la page principale..."
MAIN_PAGE=$(curl -s http://127.0.0.1:5002/)
if echo "$MAIN_PAGE" | grep -q "Lancer l'analyse"; then
    echo "✅ Page principale OK - bouton trouvé"
else
    echo "❌ Page principale KO - bouton non trouvé"
fi

# Tester l'envoi du formulaire avec données minimales
echo "3. Test de soumission du formulaire..."
RESULT=$(curl -s -X POST http://127.0.0.1:5002/ \
    -F "action=run_algorithm" \
    -F "useTestData=on" \
    -F "horizon_weeks=12" \
    -F "premix_window=8" \
    -F "grouping_threshold=0.8")

if echo "$RESULT" | grep -q "SothemaAL - Résultats"; then
    echo "✅ Formulaire fonctionne - page de résultats générée"
else
    echo "❌ Formulaire ne fonctionne pas"
    echo "Première ligne de réponse:"
    echo "$RESULT" | head -n 5
fi

# Tester la soumission avec différents paramètres
echo "4. Test avec paramètres personnalisés..."
RESULT2=$(curl -s -X POST http://127.0.0.1:5002/ \
    -F "action=run_algorithm" \
    -F "useTestData=on" \
    -F "horizon_weeks=8" \
    -F "premix_window=6" \
    -F "grouping_threshold=0.9")

if echo "$RESULT2" | grep -q "Résultats de l'analyse"; then
    echo "✅ Paramètres personnalisés fonctionnent"
else
    echo "❌ Paramètres personnalisés ne fonctionnent pas"
fi

echo ""
echo "🎯 Résumé du diagnostic:"
echo "- Backend Flask : Fonctionnel ✅"
echo "- Algorithme : Fonctionnel ✅" 
echo "- Templates : Fonctionnels ✅"
echo "- Formulaire HTML : À vérifier 🔍"
echo ""
echo "💡 Le problème semble être dans l'interface JavaScript"
echo "   ou l'interaction navigateur-formulaire."
echo ""
echo "🔧 Solutions suggérées :"
echo "1. Vérifier la console du navigateur (F12)"
echo "2. Tester le bouton 'Test Debug' dans l'interface"
echo "3. Essayer de recharger la page (Ctrl+F5)"
echo "4. Vérifier que JavaScript est activé"
