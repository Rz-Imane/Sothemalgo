#!/bin/bash

# Script de vérification post-déploiement
# Usage: ./verify_deployment.sh

echo "=== Vérification du déploiement Sothemalgo ==="

SERVER_IP="46.4.63.121"
APP_DIR="/opt/sothemalgo"

# 1. Vérification des services
echo "1. Vérification des services..."

echo "   Supervisor:"
sudo supervisorctl status | grep sothemalgo

echo "   Nginx:"
sudo systemctl status nginx --no-pager -l

echo "   Processus Python:"
ps aux | grep gunicorn | grep -v grep

# 2. Vérification des ports
echo ""
echo "2. Vérification des ports..."
echo "   Port 80 (nginx):"
sudo netstat -tlnp | grep :80

echo "   Port 5000 (gunicorn):"
sudo netstat -tlnp | grep :5000

# 3. Test de connectivité locale
echo ""
echo "3. Test de connectivité locale..."
if curl -s http://localhost > /dev/null; then
    echo "   ✅ Application répond localement"
else
    echo "   ❌ Application ne répond pas localement"
fi

# 4. Test de connectivité externe
echo ""
echo "4. Test de connectivité externe..."
if curl -s http://$SERVER_IP > /dev/null; then
    echo "   ✅ Application accessible depuis l'extérieur"
else
    echo "   ❌ Application non accessible depuis l'extérieur"
fi

# 5. Vérification des logs
echo ""
echo "5. Dernières lignes des logs..."
echo "   Logs Gunicorn:"
if [ -f "$APP_DIR/logs/gunicorn.log" ]; then
    tail -5 "$APP_DIR/logs/gunicorn.log"
else
    echo "   Aucun log Gunicorn trouvé"
fi

echo ""
echo "   Logs Nginx Error:"
if [ -f "/var/log/nginx/sothemalgo_error.log" ]; then
    tail -5 "/var/log/nginx/sothemalgo_error.log"
else
    echo "   Aucune erreur Nginx récente"
fi

# 6. Vérification des permissions
echo ""
echo "6. Vérification des permissions..."
ls -la $APP_DIR | head -5

# 7. Statut final
echo ""
echo "=== Résumé ==="
if curl -s http://$SERVER_IP > /dev/null; then
    echo "🎉 Application Sothemalgo opérationnelle !"
    echo "🌐 URL: http://$SERVER_IP"
else
    echo "⚠️  Problème détecté, vérifiez les logs ci-dessus"
fi

echo ""
echo "Commandes utiles:"
echo "  sudo supervisorctl restart sothemalgo-gunicorn"
echo "  sudo systemctl restart nginx"
echo "  sudo tail -f $APP_DIR/logs/gunicorn.log"
echo "  curl -v http://$SERVER_IP"
