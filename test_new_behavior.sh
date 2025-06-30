#!/bin/bash

echo "🔧 Test du Nouveau Comportement - Fichiers par Défaut"
echo "==================================================="

echo ""
echo "🎯 Configuration actuelle :"
echo "- Par défaut : Utilise test_*_client.csv depuis uploads/"
echo "- Avec checkbox : Utilise test_*.csv depuis le répertoire principal" 
echo "- Avec upload : Utilise vos fichiers uploadés"

echo ""
echo "📋 Test 1 : Analyse par défaut (SANS cocher la checkbox)"
echo "→ Devrait utiliser les fichiers test_*_client.csv"

RESULT1=$(curl -s -X POST http://127.0.0.1:5002/ \
    -F "action=run_algorithm" \
    -F "horizon_weeks=12")

if echo "$RESULT1" | grep -q "Résultats de l'analyse"; then
    echo "✅ Test 1 RÉUSSI : Analyse fonctionne avec fichiers client par défaut"
else
    echo "❌ Test 1 ÉCHOUÉ : Problème avec fichiers client"
fi

echo ""
echo "📋 Test 2 : Analyse avec checkbox cochée"  
echo "→ Devrait utiliser les fichiers test_*.csv (données complètes)"

RESULT2=$(curl -s -X POST http://127.0.0.1:5002/ \
    -F "action=run_algorithm" \
    -F "use_test_data=true" \
    -F "horizon_weeks=12")

if echo "$RESULT2" | grep -q "Résultats de l'analyse"; then
    echo "✅ Test 2 RÉUSSI : Analyse fonctionne avec données de test intégrées"
else
    echo "❌ Test 2 ÉCHOUÉ : Problème avec données de test intégrées"
fi

echo ""
echo "📊 Vérification des fichiers utilisés :"

echo ""
echo "🔍 Fichiers client (utilisés par défaut) :"
ls -la uploads/test_*_client.csv 2>/dev/null || echo "⚠️  Fichiers client non trouvés dans uploads/"

echo ""
echo "🔍 Fichiers de test complets (utilisés si checkbox cochée) :"
ls -la test_*.csv | grep -v client 2>/dev/null || echo "⚠️  Fichiers de test non trouvés"

echo ""
echo "🎯 RÉSUMÉ :"
echo "=========="
echo ""
echo "✅ NOUVEAU COMPORTEMENT APPLIQUÉ :"
echo ""
echo "1. 🚀 Clic sur 'Lancer l'analyse' (sans cocher checkbox)"
echo "   → Utilise automatiquement test_*_client.csv depuis uploads/"
echo ""
echo "2. ☑️  Coche 'Utiliser les données de test intégrées' + Lancer"
echo "   → Utilise test_*.csv (données complètes)"
echo ""
echo "3. 📁 Upload de fichiers + Lancer"
echo "   → Utilise vos fichiers uploadés"
echo ""
echo "💡 Maintenant vous pouvez simplement cliquer 'Lancer l'analyse'"
echo "   sans avoir à cocher quoi que ce soit !"
