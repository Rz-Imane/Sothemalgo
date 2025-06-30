#!/bin/bash

# Script de mise à jour pour Sothemalgo
# À exécuter sur le serveur pour mettre à jour le code

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

echo "=== Mise à jour de Sothemalgo ==="

# Vérifier que nous sommes dans le bon répertoire
if [ ! -d "$APP_DIR" ]; then
    echo "Erreur: Répertoire $APP_DIR non trouvé"
    exit 1
fi

cd $APP_DIR

# Sauvegarder les données utilisateur
echo "Sauvegarde des données utilisateur..."
sudo -u $APP_USER cp -r uploads/ uploads_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# Mettre à jour le code
echo "Mise à jour du code depuis GitHub..."
sudo -u $APP_USER git fetch origin
sudo -u $APP_USER git reset --hard origin/main

# Mettre à jour les dépendances Python
echo "Mise à jour des dépendances Python..."
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt --upgrade"

# Restaurer les données utilisateur si nécessaire
echo "Restauration des données utilisateur..."
sudo -u $APP_USER cp -r uploads_backup_*/test_*_client.csv uploads/ 2>/dev/null || true

# Redémarrer les services
echo "Redémarrage des services..."
sudo supervisorctl restart sothemalgo-gunicorn
sudo systemctl reload nginx

echo "=== Mise à jour terminée ==="
echo "Application accessible sur: http://46.4.63.121"
echo "Vérifiez les logs: sudo tail -f $APP_DIR/logs/gunicorn.log"
