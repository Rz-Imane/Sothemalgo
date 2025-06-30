#!/bin/bash

# Script de vérification post-nettoyage du projet Sothemalgo
# Ce script vérifie que tous les composants essentiels fonctionnent correctement

echo "🧹 Vérification post-nettoyage du projet Sothemalgo..."
echo "=================================================="

# Vérification de la structure des fichiers essentiels
echo ""
echo "📁 Vérification de la structure des fichiers essentiels..."

required_files=(
    "sothemalgo_grouper.py"
    "sothemalgo_web.py"
    "config.py"
    "web_utils.py"
    "README.md"
    "requirements.txt"
    "test_new_algo.py"
    "start_web.sh"
)

missing_files=()
for file in "${required_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "✅ $file"
    else
        echo "❌ $file (MANQUANT)"
        missing_files+=("$file")
    fi
done

required_dirs=(
    "templates"
    "static"
    "uploads"
)

for dir in "${required_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        echo "✅ $dir/"
    else
        echo "❌ $dir/ (MANQUANT)"
        missing_files+=("$dir/")
    fi
done

# Vérification des données de test
echo ""
echo "📊 Vérification des données de test..."
test_files=(
    "test_besoins.csv"
    "test_nomenclature.csv"
    "test_operations.csv"
    "test_posts.csv"
    "test_post_unavailability.csv"
)

for file in "${test_files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "✅ $file"
    else
        echo "❌ $file (MANQUANT)"
        missing_files+=("$file")
    fi
done

# Test de syntaxe Python
echo ""
echo "🐍 Vérification de la syntaxe Python..."

python_files=(
    "sothemalgo_grouper.py"
    "sothemalgo_web.py"
    "config.py"
    "web_utils.py"
    "test_new_algo.py"
)

syntax_errors=0
for file in "${python_files[@]}"; do
    if [[ -f "$file" ]]; then
        if python3 -m py_compile "$file" 2>/dev/null; then
            echo "✅ $file (syntaxe correcte)"
        else
            echo "❌ $file (erreur de syntaxe)"
            syntax_errors=$((syntax_errors + 1))
        fi
    fi
done

# Test de l'algorithme principal
echo ""
echo "🔧 Test de l'algorithme principal..."
if [[ -f "test_new_algo.py" ]] && python3 test_new_algo.py 2>/dev/null; then
    echo "✅ Algorithme principal fonctionne"
else
    echo "❌ Échec du test de l'algorithme principal"
    syntax_errors=$((syntax_errors + 1))
fi

# Résumé final
echo ""
echo "📋 RÉSUMÉ DE LA VÉRIFICATION"
echo "============================"

if [[ ${#missing_files[@]} -eq 0 ]] && [[ $syntax_errors -eq 0 ]]; then
    echo "🎉 SUCCÈS : Le projet est propre et fonctionnel !"
    echo "   - Tous les fichiers essentiels sont présents"
    echo "   - Aucune erreur de syntaxe détectée"
    echo "   - L'algorithme principal fonctionne correctement"
    echo ""
    echo "🚀 Le projet est prêt pour le déploiement !"
    exit 0
else
    echo "⚠️  ATTENTION : Des problèmes ont été détectés"
    
    if [[ ${#missing_files[@]} -gt 0 ]]; then
        echo "   Fichiers manquants :"
        for file in "${missing_files[@]}"; do
            echo "     - $file"
        done
    fi
    
    if [[ $syntax_errors -gt 0 ]]; then
        echo "   Erreurs de syntaxe ou d'exécution détectées : $syntax_errors"
    fi
    
    echo ""
    echo "❌ Veuillez corriger ces problèmes avant le déploiement."
    exit 1
fi
