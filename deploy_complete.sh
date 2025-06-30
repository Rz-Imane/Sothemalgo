#!/bin/bash

# Script de déploiement complet pour Sothemalgo sur Ubuntu Server
# Usage: ./deploy_complete.sh

set -e  # Arrêter en cas d'erreur

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"
NGINX_SITE="sothemalgo"

echo "=== Déploiement complet de Sothemalgo ==="

# 1. Vérifier les prérequis
echo "Vérification des prérequis..."
if ! command -v python3 &> /dev/null; then
    echo "Python3 n'est pas installé. Installation..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv
fi

if ! command -v nginx &> /dev/null; then
    echo "Nginx n'est pas installé. Installation..."
    sudo apt install -y nginx
fi

if ! command -v supervisorctl &> /dev/null; then
    echo "Supervisor n'est pas installé. Installation..."
    sudo apt install -y supervisor
fi

# 2. Créer l'utilisateur et les répertoires
echo "Configuration de l'utilisateur et des répertoires..."
sudo useradd -m -s /bin/bash $APP_USER 2>/dev/null || echo "Utilisateur $APP_USER existe déjà"
sudo mkdir -p $APP_DIR
sudo chown $APP_USER:$APP_USER $APP_DIR

# 3. Installer Gunicorn dans requirements
echo "Mise à jour des requirements pour la production..."
if ! grep -q "gunicorn" requirements.txt; then
    echo "gunicorn==21.2.0" >> requirements.txt
fi

# 4. Clonage du repository depuis GitHub
echo "Configuration du repository Sothemalgo..."
cd $APP_DIR

# Vérifier si c'est un repository git existant
if [ -d ".git" ]; then
    echo "Repository existe, mise à jour..."
    # Corriger les permissions git
    sudo git config --global --add safe.directory $APP_DIR
    sudo -u $APP_USER git config --global --add safe.directory $APP_DIR
    sudo -u $APP_USER git pull origin main
else
    echo "Nouveau clonage depuis GitHub..."
    sudo -u $APP_USER git clone https://github.com/abdobzx/sothema-algo.git .
fi

# 5. Configuration de l'environnement Python
echo "Configuration de l'environnement Python..."
cd $APP_DIR
sudo -u $APP_USER python3 -m venv sothemalgo_env
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install --upgrade pip"
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"

# 6. Créer les répertoires nécessaires
sudo -u $APP_USER mkdir -p $APP_DIR/{logs,uploads,static,templates}

# 7. Configuration Supervisor
echo "Configuration de Supervisor..."
sudo cp sothemalgo.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update

# 8. Configuration Nginx
echo "Configuration de Nginx..."
sudo cp nginx_sothemalgo.conf /etc/nginx/sites-available/$NGINX_SITE
sudo ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
if [ $? -eq 0 ]; then
    # Démarrer nginx s'il n'est pas actif
    if ! systemctl is-active --quiet nginx; then
        sudo systemctl start nginx
    else
        sudo systemctl reload nginx
    fi
    echo "Nginx configuré et démarré avec succès"
else
    echo "Erreur dans la configuration Nginx"
    exit 1
fi

# 9. Démarrage des services
echo "Démarrage des services..."
sudo supervisorctl start sothemalgo-gunicorn
sudo systemctl enable nginx
sudo systemctl enable supervisor

# 10. Configuration du firewall (optionnel)
echo "Configuration du firewall..."
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
# sudo ufw --force enable  # Décommentez si vous voulez activer le firewall

echo "=== Déploiement terminé ==="
echo "Application accessible sur: http://46.4.63.121"
echo "Logs disponibles dans: $APP_DIR/logs/"
echo "Commandes utiles:"
echo "  sudo supervisorctl status"
echo "  sudo supervisorctl restart sothemalgo-gunicorn"
echo "  sudo tail -f $APP_DIR/logs/gunicorn.log"
