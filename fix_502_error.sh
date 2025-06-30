#!/bin/bash

# Script de réparation pour erreur 502 Bad Gateway
# Usage: ./fix_502_error.sh

echo "=== Réparation erreur 502 Bad Gateway ==="

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

# 1. Arrêter tous les services
echo "1. Arrêt des services..."
sudo supervisorctl stop sothemalgo-gunicorn
sudo systemctl stop nginx

# 2. Corriger les permissions
echo "2. Correction des permissions..."
sudo chown -R $APP_USER:$APP_USER $APP_DIR
sudo chmod -R 755 $APP_DIR
sudo chmod +x $APP_DIR/*.sh

# 3. Vérifier l'environnement Python
echo "3. Vérification de l'environnement Python..."
cd $APP_DIR
if [ ! -d "sothemalgo_env" ]; then
    echo "   Création de l'environnement virtuel..."
    sudo -u $APP_USER python3 -m venv sothemalgo_env
fi

echo "   Installation/mise à jour des dépendances..."
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install --upgrade pip"
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"

# 4. Test de l'application Flask
echo "4. Test de l'application Flask..."
if sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && python -c 'import sothemalgo_web; print(\"Import OK\")'"; then
    echo "   ✅ Application Flask fonctionne"
else
    echo "   ❌ Problème avec l'application Flask"
    echo "   Tentative de réparation des imports..."
    cd $APP_DIR
    sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install --force-reinstall flask gunicorn"
fi

# 5. Créer les répertoires de logs
echo "5. Création des répertoires de logs..."
sudo -u $APP_USER mkdir -p $APP_DIR/logs
sudo -u $APP_USER mkdir -p $APP_DIR/uploads

# 6. Test manuel de Gunicorn
echo "6. Test manuel de Gunicorn..."
cd $APP_DIR
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && timeout 5s gunicorn --bind 127.0.0.1:5000 --timeout 10 sothemalgo_web:app" &
GUNICORN_PID=$!
sleep 3

if curl -s http://localhost:5000 > /dev/null 2>&1; then
    echo "   ✅ Gunicorn fonctionne manuellement"
    kill $GUNICORN_PID 2>/dev/null
else
    echo "   ❌ Gunicorn ne fonctionne pas manuellement"
    kill $GUNICORN_PID 2>/dev/null
    echo "   Vérification des erreurs..."
    sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && python sothemalgo_web.py" &
    FLASK_PID=$!
    sleep 2
    kill $FLASK_PID 2>/dev/null
fi

# 7. Reconfigurer Supervisor
echo "7. Reconfiguration de Supervisor..."
sudo cp sothemalgo.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update

# 8. Redémarrer les services
echo "8. Redémarrage des services..."
sudo supervisorctl start sothemalgo-gunicorn
sleep 3
sudo systemctl start nginx

# 9. Vérification finale
echo "9. Vérification finale..."
sleep 2

echo "   Statut des services:"
sudo supervisorctl status sothemalgo-gunicorn
sudo systemctl status nginx --no-pager -l | head -3

echo "   Test des ports:"
sudo netstat -tlnp | grep -E "(5000|80)"

echo "   Test final:"
if curl -s http://localhost:5000 > /dev/null; then
    echo "   ✅ Gunicorn: OK"
else
    echo "   ❌ Gunicorn: Échec"
fi

if curl -s http://localhost > /dev/null; then
    echo "   ✅ Nginx: OK"
else
    echo "   ❌ Nginx: Échec"
fi

echo ""
echo "=== Réparation terminée ==="
echo "Testez maintenant: curl http://46.4.63.121"
echo "Logs: sudo tail -f $APP_DIR/logs/gunicorn.log"
