#!/bin/bash

# Script pour créer un package de déploiement
# Usage: ./create_deployment_package.sh

PACKAGE_NAME="sothemalgo-deployment-$(date +%Y%m%d-%H%M%S)"
TEMP_DIR="/tmp/$PACKAGE_NAME"

echo "=== Création du package de déploiement ==="

# Créer le répertoire temporaire
mkdir -p "$TEMP_DIR"

# Copier les fichiers nécessaires
echo "Copie des fichiers..."
cp -r . "$TEMP_DIR/"

# Nettoyer les fichiers non nécessaires
echo "Nettoyage..."
cd "$TEMP_DIR"
rm -rf __pycache__/
rm -rf .git/
rm -rf sothemalgo_env/
rm -rf logs/
rm -f *.log
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete

# Créer l'archive
echo "Création de l'archive..."
cd /tmp
tar -czf "${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME"

# Déplacer l'archive vers le répertoire original
mv "${PACKAGE_NAME}.tar.gz" "/Users/abderrahman/Desktop/"

# Nettoyer
rm -rf "$TEMP_DIR"

echo "Package créé: /Users/abderrahman/Desktop/${PACKAGE_NAME}.tar.gz"
echo "Pour déployer sur le serveur:"
echo "  scp /Users/abderrahman/Desktop/${PACKAGE_NAME}.tar.gz user@server:/tmp/"
echo "  ssh user@server"
echo "  cd /tmp && tar -xzf ${PACKAGE_NAME}.tar.gz"
echo "  sudo cp -r ${PACKAGE_NAME}/* /opt/sothemalgo/"
echo "  cd /opt/sothemalgo && sudo ./deploy_complete.sh"
