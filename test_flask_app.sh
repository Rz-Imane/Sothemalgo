#!/bin/bash

# Script de test rapide de l'application Flask
# Usage: ./test_flask_app.sh

echo "=== Test de l'application Flask Sothemalgo ==="

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

cd $APP_DIR

echo "1. Test d'import de l'application Flask..."
if sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && python -c 'import sothemalgo_web; print(\"✅ Import réussi\"); print(\"BASE_DIR:\", sothemalgo_web.BASE_DIR); print(\"UPLOAD_FOLDER:\", sothemalgo_web.app.config[\"UPLOAD_FOLDER\"])'"; then
    echo "   ✅ Application Flask OK"
else
    echo "   ❌ Problème d'import Flask"
    exit 1
fi

echo ""
echo "2. Test de démarrage Flask (mode développement)..."
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && timeout 5s python sothemalgo_web.py" &
FLASK_PID=$!
sleep 3

if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "   ✅ Flask fonctionne en mode développement"
    kill $FLASK_PID 2>/dev/null
else
    echo "   ❌ Flask ne fonctionne pas en mode développement"
    kill $FLASK_PID 2>/dev/null
fi

echo ""
echo "3. Test de démarrage Gunicorn..."
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && timeout 5s gunicorn --bind 127.0.0.1:5000 --timeout 10 sothemalgo_web:app" &
GUNICORN_PID=$!
sleep 3

if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "   ✅ Gunicorn fonctionne"
    kill $GUNICORN_PID 2>/dev/null
else
    echo "   ❌ Gunicorn ne fonctionne pas"
    kill $GUNICORN_PID 2>/dev/null
fi

echo ""
echo "4. Vérification des répertoires..."
echo "   Répertoire uploads: $(ls -la uploads/ 2>/dev/null | wc -l) fichiers"
echo "   Répertoire logs: $(ls -la logs/ 2>/dev/null | wc -l) fichiers"

echo ""
echo "=== Test terminé ==="
