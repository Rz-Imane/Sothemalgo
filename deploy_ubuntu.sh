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

# 4. Copie des fichiers de l'application
echo "Copie des fichiers..."
# Cette partie sera adaptée selon votre méthode de transfert (git, scp, etc.)

echo "Script de base terminé. Suivez les instructions suivantes pour compléter le déploiement."
