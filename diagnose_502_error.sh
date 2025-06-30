#!/bin/bash

# Script de diagnostic pour erreur 502 Bad Gateway
# Usage: ./diagnose_502_error.sh

echo "=== Diagnostic erreur 502 Bad Gateway ==="

APP_DIR="/opt/sothemalgo"
SERVER_IP="46.4.63.121"

# 1. Vérifier le statut de Nginx
echo "1. Statut Nginx:"
sudo systemctl status nginx --no-pager -l | head -10

# 2. Vérifier le statut de Supervisor
echo ""
echo "2. Statut Supervisor:"
sudo supervisorctl status

# 3. Vérifier les ports
echo ""
echo "3. Ports ouverts:"
echo "   Port 80 (Nginx):"
sudo netstat -tlnp | grep :80
echo "   Port 5000 (Gunicorn):"
sudo netstat -tlnp | grep :5000

# 4. Test direct de Gunicorn
echo ""
echo "4. Test direct de Gunicorn:"
if curl -s http://localhost:5000 > /dev/null; then
    echo "   ✅ Gunicorn répond"
else
    echo "   ❌ Gunicorn ne répond pas"
fi

# 5. Vérifier les logs
echo ""
echo "5. Logs récents:"
echo "   === Logs Gunicorn ==="
if [ -f "$APP_DIR/logs/gunicorn.log" ]; then
    tail -15 "$APP_DIR/logs/gunicorn.log"
else
    echo "   Aucun log Gunicorn trouvé"
fi

echo ""
echo "   === Logs Nginx Error ==="
if [ -f "/var/log/nginx/sothemalgo_error.log" ]; then
    tail -10 "/var/log/nginx/sothemalgo_error.log"
else
    echo "   Aucune erreur Nginx récente"
fi

echo ""
echo "   === Logs Nginx Access ==="
if [ -f "/var/log/nginx/sothemalgo_access.log" ]; then
    tail -5 "/var/log/nginx/sothemalgo_access.log"
else
    echo "   Aucun accès Nginx récent"
fi

# 6. Vérifier la configuration Flask
echo ""
echo "6. Test de l'application Flask:"
cd $APP_DIR
if sudo -u sothemalgo bash -c "source sothemalgo_env/bin/activate && python -c 'import sothemalgo_web; print(\"Flask app import OK\")'"; then
    echo "   ✅ Application Flask peut être importée"
else
    echo "   ❌ Problème d'import Flask"
fi

# 7. Vérifier les permissions
echo ""
echo "7. Permissions du répertoire:"
ls -la $APP_DIR | head -5

# 8. Solutions recommandées
echo ""
echo "=== Solutions recommandées ==="
echo "1. Redémarrer Gunicorn:"
echo "   sudo supervisorctl restart sothemalgo-gunicorn"
echo ""
echo "2. Redémarrer tous les services:"
echo "   sudo systemctl restart nginx"
echo "   sudo supervisorctl restart all"
echo ""
echo "3. Vérifier manuellement Gunicorn:"
echo "   cd $APP_DIR"
echo "   sudo -u sothemalgo bash -c 'source sothemalgo_env/bin/activate && gunicorn --bind 127.0.0.1:5000 sothemalgo_web:app'"
echo ""
echo "4. Voir les logs en temps réel:"
echo "   sudo tail -f $APP_DIR/logs/gunicorn.log"
