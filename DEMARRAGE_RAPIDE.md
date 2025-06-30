# 🚀 Commandes Rapides - Interface Web Moderne

## ⚡ Démarrage Rapide

Pour démarrer l'interface web moderne SothemaAL, utilisez l'une de ces méthodes :

### Méthode 1 : Script automatique (Recommandé)
```bash
./start_web.sh
```

### Méthode 2 : Commandes manuelles
```bash
source sothemalgo_env/bin/activate
python sothemalgo_web.py
```

### Méthode 3 : Script rapide existant
```bash
bash start_quick.sh
# Puis choisir option 2 (Interface web)
```

## 🌐 Accès à l'Interface

Une fois le serveur démarré, ouvrez votre navigateur sur :
- **URL principale** : http://localhost:5002
- **Dashboard** : http://localhost:5002/data-visualization
- **API données** : http://localhost:5002/api/visualization-data

## 🛑 Arrêt du Serveur

Dans le terminal où le serveur fonctionne :
```
Ctrl + C
```

## 🔧 Dépannage Rapide

### Port déjà utilisé
```bash
# Libérer le port 5002
lsof -ti:5002 | xargs kill -9
```

### Problème environnement virtuel
```bash
# Réactiver l'environnement
source sothemalgo_env/bin/activate
```

### Dépendances manquantes
```bash
pip install flask waitress
```

## ✨ Nouvelles Fonctionnalités

### 🎨 Interface Moderne
- Design professionnel avec thème sombre
- Drag & Drop pour les fichiers
- Animations fluides
- Interface responsive

### 📊 Dashboard Avancé
- Graphiques interactifs Chart.js
- Métriques temps réel
- Filtres avancés
- Export des données

### 🔄 API REST
- Données structurées JSON
- Endpoint `/api/visualization-data`
- Compatible avec outils externes

## 🎯 Utilisation Simple

1. **Lancer** : `./start_web.sh`
2. **Ouvrir** : http://localhost:5002
3. **Tester** : Activez "Données de test"
4. **Analyser** : Cliquez "Lancer l'analyse"
5. **Visualiser** : Consultez les résultats et graphiques

**L'interface est maintenant moderne et prête !** 🚀
