# Guide de déploiement rapide - Serveur 46.4.63.121

## Déploiement en une commande

```bash
# Sur le serveur 46.4.63.121
curl -s https://raw.githubusercontent.com/abdobzx/sothema-algo/main/deploy_server_46.4.63.121.sh | sudo bash
```

## Déploiement manuel

### 1. Connexion au serveur
```bash
ssh root@46.4.63.121
# ou
ssh user@46.4.63.121
```

### 2. Clonage et déploiement
```bash
sudo mkdir -p /opt/sothemalgo
cd /opt/sothemalgo
sudo git clone https://github.com/abdobzx/sothema-algo.git .
sudo chmod +x *.sh
sudo ./deploy_server_46.4.63.121.sh
```

### 3. Vérification
```bash
# Vérifier que l'application fonctionne
curl http://46.4.63.121

# Vérifier les services
sudo supervisorctl status
sudo systemctl status nginx

# Voir les logs
sudo tail -f /opt/sothemalgo/logs/gunicorn.log
```

## Accès à l'application

🌐 **URL:** http://46.4.63.121

## Maintenance

### Mise à jour de l'application
```bash
cd /opt/sothemalgo
sudo ./update_production.sh
```

### Redémarrage des services
```bash
sudo supervisorctl restart sothemalgo-gunicorn
sudo systemctl restart nginx
```

### Surveillance des logs
```bash
# Logs de l'application
sudo tail -f /opt/sothemalgo/logs/gunicorn.log

# Logs Nginx
sudo tail -f /var/log/nginx/sothemalgo_error.log
sudo tail -f /var/log/nginx/sothemalgo_access.log
```

### Sauvegarde des données
```bash
# Sauvegarder les uploads utilisateur
sudo cp -r /opt/sothemalgo/uploads /backup/sothemalgo_uploads_$(date +%Y%m%d)
```

## Dépannage

### L'application ne répond pas
```bash
# Vérifier le processus
sudo supervisorctl status sothemalgo-gunicorn

# Redémarrer
sudo supervisorctl restart sothemalgo-gunicorn

# Vérifier les logs
sudo tail -100 /opt/sothemalgo/logs/gunicorn.log
```

### Nginx ne fonctionne pas
```bash
# Tester la configuration
sudo nginx -t

# Redémarrer
sudo systemctl restart nginx

# Vérifier les logs
sudo tail -f /var/log/nginx/error.log
```

### Problèmes de permissions
```bash
sudo chown -R sothemalgo:sothemalgo /opt/sothemalgo
sudo chmod -R 755 /opt/sothemalgo
```

## Sécurité

### Firewall (déjà configuré par le script)
```bash
sudo ufw status
```

### SSL/HTTPS (optionnel)
```bash
# Installer Certbot
sudo apt install certbot python3-certbot-nginx

# Obtenir un certificat (nécessite un nom de domaine)
# sudo certbot --nginx -d yourdomain.com
```

## Configuration avancée

### Variables d'environnement
```bash
# Éditer le fichier de configuration
sudo nano /opt/sothemalgo/config_production.py
```

### Monitoring
```bash
# Installer htop pour surveiller les ressources
sudo apt install htop

# Surveiller l'utilisation
htop
```
