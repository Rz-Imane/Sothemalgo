# Guide de déploiement Sothemalgo sur Ubuntu Server

## Prérequis
- Serveur Ubuntu 20.04 LTS ou plus récent
- Accès root ou sudo
- Au moins 2GB de RAM et 10GB d'espace disque

## Étape 1: Préparation du serveur

```bash
# Connexion au serveur
ssh user@your-server-ip

# Mise à jour du système
sudo apt update && sudo apt upgrade -y

# Installation des dépendances
sudo apt install -y python3 python3-pip python3-venv nginx supervisor git curl
```

## Étape 2: Transfert des fichiers

### Option A: Via Git (recommandé)
```bash
sudo mkdir -p /opt/sothemalgo
sudo chown $USER:$USER /opt/sothemalgo
cd /opt/sothemalgo
git clone https://github.com/your-username/sothemalgo.git .
```

### Option B: Via SCP depuis votre machine locale
```bash
# Depuis votre machine locale
scp -r /Users/abderrahman/Desktop/Sothemalgo2/* user@your-server:/opt/sothemalgo/
```

### Option C: Via RSYNC
```bash
# Depuis votre machine locale
rsync -av --exclude='__pycache__' --exclude='*.pyc' /Users/abderrahman/Desktop/Sothemalgo2/ user@your-server:/opt/sothemalgo/
```

## Étape 3: Configuration sur le serveur

```bash
# Aller dans le répertoire
cd /opt/sothemalgo

# Rendre les scripts exécutables
chmod +x *.sh

# Exécuter le script de déploiement
sudo ./deploy_complete.sh
```

## Étape 4: Configuration manuelle si nécessaire

### Créer l'utilisateur sothemalgo
```bash
sudo useradd -m -s /bin/bash sothemalgo
sudo chown -R sothemalgo:sothemalgo /opt/sothemalgo
```

### Configurer l'environnement Python
```bash
cd /opt/sothemalgo
sudo -u sothemalgo python3 -m venv sothemalgo_env
sudo -u sothemalgo bash -c "source sothemalgo_env/bin/activate && pip install -r requirements.txt"
```

### Configurer Supervisor
```bash
sudo cp sothemalgo.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start sothemalgo-gunicorn
```

### Configurer Nginx
```bash
# Éditer le fichier de configuration pour mettre votre IP/domaine
sudo nano nginx_sothemalgo.conf
# Remplacer YOUR_DOMAIN_OR_IP par votre vraie IP ou domaine

sudo cp nginx_sothemalgo.conf /etc/nginx/sites-available/sothemalgo
sudo ln -s /etc/nginx/sites-available/sothemalgo /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Supprimer le site par défaut
sudo nginx -t
sudo systemctl reload nginx
```

## Étape 5: Configuration du firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS (si vous configurez SSL)
sudo ufw enable
```

## Étape 6: Test et vérification

```bash
# Vérifier le statut des services
sudo supervisorctl status
sudo systemctl status nginx

# Vérifier les logs
sudo tail -f /opt/sothemalgo/logs/gunicorn.log
sudo tail -f /var/log/nginx/sothemalgo_error.log

# Test de l'application
curl http://localhost
curl http://your-server-ip
```

## Étape 7: Configuration SSL (optionnel mais recommandé)

### Avec Let's Encrypt (gratuit)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Commandes utiles pour la maintenance

```bash
# Redémarrer l'application
sudo supervisorctl restart sothemalgo-gunicorn

# Voir les logs en temps réel
sudo tail -f /opt/sothemalgo/logs/gunicorn.log

# Mettre à jour l'application
cd /opt/sothemalgo
git pull origin main
sudo supervisorctl restart sothemalgo-gunicorn

# Voir l'état de tous les services
sudo supervisorctl status
sudo systemctl status nginx

# Redémarrer nginx
sudo systemctl restart nginx
```

## Dépannage

### Problème de permissions
```bash
sudo chown -R sothemalgo:sothemalgo /opt/sothemalgo
sudo chmod -R 755 /opt/sothemalgo
```

### L'application ne démarre pas
```bash
# Vérifier les logs
sudo tail -100 /opt/sothemalgo/logs/gunicorn.log
sudo supervisorctl status sothemalgo-gunicorn

# Tester manuellement
cd /opt/sothemalgo
sudo -u sothemalgo source sothemalgo_env/bin/activate
sudo -u sothemalgo python sothemalgo_web.py
```

### Nginx ne fonctionne pas
```bash
# Tester la configuration
sudo nginx -t

# Vérifier les logs
sudo tail -f /var/log/nginx/error.log
```

## Sécurité additionnelle

1. **Changez le SECRET_KEY** dans la configuration
2. **Configurez un backup automatique** des données
3. **Limitez l'accès SSH** aux IPs autorisées
4. **Configurez fail2ban** pour la protection contre les attaques
5. **Mettez à jour régulièrement** le système

## Monitoring

Pour surveiller l'application en production, vous pouvez installer:
- **htop** pour surveiller les ressources
- **logrotate** pour la rotation des logs
- **monit** ou **nagios** pour le monitoring avancé
