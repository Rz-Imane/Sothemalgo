#!/bin/bash

# Script de réparation rapide pour Sothemalgo
# Usage: ./fix_deployment.sh

echo "=== Réparation du déploiement Sothemalgo ==="

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

# 1. Corriger les permissions Git
echo "1. Correction des permissions Git..."
sudo git config --global --add safe.directory $APP_DIR
sudo -u $APP_USER git config --global --add safe.directory $APP_DIR
sudo chown -R $APP_USER:$APP_USER $APP_DIR/.git

# 2. Corriger les permissions des fichiers
echo "2. Correction des permissions des fichiers..."
sudo chown -R $APP_USER:$APP_USER $APP_DIR
sudo chmod -R 755 $APP_DIR
sudo chmod +x $APP_DIR/*.sh

# 3. Arrêter les services Docker sur le port 80 si nécessaire
echo "3. Vérification des conflits de ports..."
if docker ps | grep -q "0.0.0.0:80"; then
    echo "   Arrêt des containers Docker utilisant le port 80..."
    docker ps --format "table {{.ID}}\t{{.Ports}}" | grep "0.0.0.0:80" | awk '{print $1}' | xargs -r docker stop
fi

# 4. Redémarrer Nginx
echo "4. Redémarrage de Nginx..."
sudo systemctl stop nginx
sleep 2
sudo systemctl start nginx
sudo systemctl enable nginx

# 5. Redémarrer Supervisor
echo "5. Redémarrage de Supervisor..."
sudo supervisorctl restart sothemalgo-gunicorn
sudo systemctl enable supervisor

# 6. Vérification finale
echo "6. Vérification finale..."
sleep 5

echo "   Test local:"
if curl -s http://localhost > /dev/null; then
    echo "   ✅ OK"
else
    echo "   ❌ Échec"
fi

echo "   Test externe:"
if curl -s http://46.4.63.121 > /dev/null; then
    echo "   ✅ OK"
else
    echo "   ❌ Échec"
fi

echo ""
echo "=== Réparation terminée ==="
echo "Vérifiez avec: ./verify_deployment.sh"
