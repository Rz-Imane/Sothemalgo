#!/bin/bash

# Script d'installation de l'environnement Python pour Sothemalgo
# À exécuter après avoir copié les fichiers sur le serveur

APP_DIR="/opt/sothemalgo"
APP_USER="sothemalgo"

echo "=== Configuration de l'environnement Python ==="

# Aller dans le répertoire de l'application
cd $APP_DIR

# Créer l'environnement virtuel
echo "Création de l'environnement virtuel..."
sudo -u $APP_USER python3 -m venv sothemalgo_env

# Activer l'environnement et installer les dépendances
echo "Installation des dépendances Python..."
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install --upgrade pip"
sudo -u $APP_USER bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"

# Créer les répertoires nécessaires
echo "Création des répertoires..."
sudo -u $APP_USER mkdir -p $APP_DIR/logs
sudo -u $APP_USER mkdir -p $APP_DIR/uploads
sudo -u $APP_USER mkdir -p $APP_DIR/static
sudo -u $APP_USER mkdir -p $APP_DIR/templates

# Définir les permissions
chmod +x $APP_DIR/sothemalgo_web.py
chmod +x $APP_DIR/*.sh

echo "Environnement Python configuré avec succès !"
