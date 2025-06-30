# 🪟 Sothemalgo - Guide Windows Entreprise

## ⚠️ Important : Restrictions de permissions en entreprise

Si vous travaillez dans un environnement d'entreprise avec des restrictions sur cmd ou PowerShell, **Git Bash est la solution recommandée** car il contourne la plupart des limitations de sécurité d'entreprise.

## 🚀 Installation avec Git Bash (Recommandé en entreprise)

### Étape 1 : Installation des prérequis

1. **Python 3.8+** depuis [python.org](https://python.org) - ✅ Cocher "Add Python to PATH"
2. **Git pour Windows** depuis [git-scm.com](https://git-scm.com)

### Étape 2 : Installation de Sothemalgo

```bash
# 1. Ouvrir Git Bash (clic droit dans le dossier → "Git Bash Here")
# 2. Naviguer vers le dossier du projet
cd /c/Users/VotreNom/Desktop/Sothemalgo2

# 3. Créer un environnement virtuel (si pas encore fait)
python -m venv sothemalgo_env

# 4. Activer l'environnement virtuel (syntaxe Unix dans Git Bash)
source sothemalgo_env/Scripts/activate

# 5. Installer les dépendances depuis requirements.txt
pip install -r requirements.txt

# Ou pour une installation minimale plus rapide :
# pip install -r requirements-minimal.txt
```

### Étape 3 : Lancement

```bash
# Lancer l'interface web
source sothemalgo_env/Scripts/activate
python sothemalgo_web.py

# Tester l'algorithme
source sothemalgo_env/Scripts/activate
python test_new_algo.py

# Vérifier l'installation
source sothemalgo_env/Scripts/activate
python test_dependencies.py
```

## 🛠️ Création de raccourcis pratiques

### Script de lancement automatique

Créez un fichier `lancer_sothemalgo.sh` dans votre dossier projet :

```bash
#!/bin/bash
cd /c/Users/VotreNom/Desktop/Sothemalgo2
source sothemalgo_env/Scripts/activate
python sothemalgo_web.py
read -p "Appuyez sur Entrée pour fermer..."
```

### Raccourci bureau avec Git Bash

1. Clic droit sur le bureau → Nouveau → Raccourci
2. Cible : `"C:\Program Files\Git\bin\bash.exe" -c "cd /c/Users/VotreNom/Desktop/Sothemalgo2 && source sothemalgo_env/Scripts/activate && python sothemalgo_web.py"`
3. Nom : "Sothemalgo"

## ⚡ Commandes rapides Git Bash

```bash
# Navigation Windows dans Git Bash
cd /c/Users/VotreNom/Desktop/Sothemalgo2

# Activation environnement
source sothemalgo_env/Scripts/activate

# Lancement rapide web
python sothemalgo_web.py

# Test rapide algorithme
python test_new_algo.py

# Validation dépendances
python test_dependencies.py

# Menu interactif (si pas de restrictions sur bash)
bash start_quick.sh
```

## 🔧 Résolution de problèmes entreprise

### ❌ Problème : "Git Bash non trouvé"

**Solution :**

1. Installer Git pour Windows depuis [git-scm.com](https://git-scm.com)
2. Redémarrer
3. Clic droit dans un dossier → "Git Bash Here" devrait apparaître

### ❌ Problème : "python n'est pas reconnu dans Git Bash"

**Solution :**

```bash
# Vérifier la version Python dans Git Bash
python --version
# Si erreur, utiliser py au lieu de python
py --version
# Puis utiliser py au lieu de python dans toutes les commandes
```

### ❌ Problème : "Permission denied" dans Git Bash

**Solution :**

```bash
# Donner les permissions d'exécution aux scripts
chmod +x start_quick.sh
chmod +x verify_project.sh
chmod +x show_dependencies.sh
```

### ❌ Problème : Chemin Windows vs Unix

**Solution :**

```bash
# Windows : C:\Users\VotreNom\Desktop\Sothemalgo2
# Git Bash : /c/Users/VotreNom/Desktop/Sothemalgo2
# Utiliser la notation Unix (/) dans Git Bash
```

## 🌐 Accès à l'interface

Une fois lancé avec Git Bash, l'interface web est accessible sur :

- **URL** : [http://localhost:5002](http://localhost:5002)
- **Compatible** : Chrome, Firefox, Edge, Safari
- **Réseau d'entreprise** : Généralement autorisé sur localhost

## 💡 Avantages de Git Bash en entreprise

- ✅ **Contournement des restrictions** : Git Bash émule Unix, souvent moins restreint
- ✅ **Syntaxe standard** : Même commandes que Linux/Mac
- ✅ **Pas d'admin requis** : Installation possible sans droits administrateur
- ✅ **Portable** : Peut fonctionner depuis une clé USB
- ✅ **Scripts bash** : Support des scripts Unix/Linux

## 📞 Support spécifique entreprise

Si vous rencontrez des problèmes spécifiques à votre environnement d'entreprise :

1. **Proxy d'entreprise** : Configurer pip avec le proxy

```bash
pip install -r requirements.txt --proxy http://proxy.entreprise.com:8080
```

1. **Restrictions réseau** : Vérifier que localhost:5002 est accessible

1. **Antivirus** : Ajouter le dossier Sothemalgo aux exceptions si nécessaire

1. **Dépendances** : Utiliser `requirements-minimal.txt` si installation complète bloquée

---

**🎯 En résumé** : Git Bash est votre meilleur ami en entreprise pour contourner les restrictions Windows et utiliser Sothemalgo efficacement !
