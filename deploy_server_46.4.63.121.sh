#!/bin/bash

# Script de déploiement spécifique pour le serveur 46.4.63.121
# Usage: ./deploy_server_46.4.63.121.sh

echo "=== Déploiement Sothemalgo sur serveur 46.4.63.121 ==="

# Configuration spécifique du serveur
SERVER_IP="46.4.63.121"
APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

# 1. Vérification des prérequis
echo "Vérification de la connectivité..."
if ! ping -c 1 8.8.8.8 &> /dev/null; then
    echo "Attention: Pas de connectivité Internet détectée"
fi

# 2. Installation des dépendances système
echo "Installation des dépendances système..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx supervisor git curl ufw

# 3. Configuration du firewall
echo "Configuration du firewall..."
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
echo "y" | sudo ufw enable

# 4. Création de l'utilisateur et des répertoires
echo "Configuration utilisateur et répertoires..."
sudo useradd -m -s /bin/bash $APP_USER 2>/dev/null || echo "Utilisateur $APP_USER existe déjà"
sudo usermod -aG www-data $APP_USER
sudo mkdir -p $APP_DIR
sudo chown $APP_USER:$APP_USER $APP_DIR

# 5. Clonage du repository
echo "Clonage du repository Sothemalgo..."
cd $APP_DIR
if [ -d ".git" ]; then
    echo "Repository existe, mise à jour..."
    sudo -u $APP_USER git pull origin main
else
    echo "Nouveau clonage..."
    sudo -u $APP_USER git clone https://github.com/abdobzx/sothema-algo.git .
fi

# 6. Configuration de l'environnement Python
echo "Configuration de l'environnement Python..."
sudo -u $APP_USER python3 -m venv sothemalgo_env
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install --upgrade pip"
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"

# 7. Création des répertoires nécessaires
sudo -u $APP_USER mkdir -p $APP_DIR/{logs,uploads,static,templates}

# 8. Configuration Supervisor
echo "Configuration de Supervisor..."
sudo cp sothemalgo.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl restart sothemalgo-gunicorn

# 9. Configuration Nginx
echo "Configuration de Nginx..."
sudo cp nginx_sothemalgo.conf /etc/nginx/sites-available/sothemalgo
sudo ln -sf /etc/nginx/sites-available/sothemalgo /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
if [ $? -eq 0 ]; then
    sudo systemctl reload nginx
    echo "Nginx configuré avec succès"
else
    echo "Erreur dans la configuration Nginx"
    exit 1
fi

# 10. Démarrage et activation des services
echo "Démarrage des services..."
sudo systemctl enable nginx
sudo systemctl enable supervisor
sudo supervisorctl start sothemalgo-gunicorn

# 11. Vérification finale
echo "Vérification finale..."
sleep 5
if curl -s http://localhost > /dev/null; then
    echo "✅ Application fonctionne localement"
else
    echo "❌ Problème avec l'application locale"
fi

echo ""
echo "=== Déploiement terminé ==="
echo "🌐 Application accessible sur: http://$SERVER_IP"
echo "📁 Répertoire: $APP_DIR"
echo "📋 Logs: $APP_DIR/logs/"
echo ""
echo "Commandes utiles:"
echo "  sudo supervisorctl status"
echo "  sudo supervisorctl restart sothemalgo-gunicorn"
echo "  sudo tail -f $APP_DIR/logs/gunicorn.log"
echo "  sudo systemctl status nginx"
echo "  curl http://$SERVER_IP"
echo ""
echo "Pour mettre à jour: sudo $APP_DIR/update_production.sh"
