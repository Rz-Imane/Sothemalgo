#!/bin/bash

# Script de déploiement pour Ubuntu Server
# Installation automatique de Sothemalgo

echo "=== Déploiement Sothemalgo sur Ubuntu Server ==="

# 1. Installation des dépendances système
echo "Installation des dépendances système..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx supervisor git curl

# 2. Création de l'utilisateur de l'application
echo "Création de l'utilisateur sothemalgo..."
sudo useradd -m -s /bin/bash sothemalgo
sudo usermod -aG www-data sothemalgo

# 3. Création du répertoire de l'application
echo "Création du répertoire de l'application..."
sudo mkdir -p /opt/sothemalgo
sudo chown sothemalgo:sothemalgo /opt/sothemalgo

# 4. Copie des fichiers de l'application via Git
echo "Clonage du repository depuis GitHub..."
cd /opt/sothemalgo
sudo -u sothemalgo git clone https://github.com/abdobzx/sothema-algo.git .

# 5. Configuration de l'environnement Python
echo "Configuration de l'environnement Python..."
sudo -u sothemalgo python3 -m venv sothemalgo_env
sudo -u sothemalgo bash -c "source sothemalgo_env/bin/activate && pip install --upgrade pip"
sudo -u sothemalgo bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"

# 6. Création des répertoires supplémentaires
sudo -u sothemalgo mkdir -p logs uploads

echo "Déploiement de base terminé. Exécutez maintenant ./deploy_complete.sh pour finaliser."
