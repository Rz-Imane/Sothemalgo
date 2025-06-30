# 🎨 Guide de la Nouvelle Interface SothemaAL

## ✨ Interface Web Moderne - Guide d'Utilisation

La nouvelle interface SothemaAL a été entièrement redesignée pour offrir une expérience utilisateur professionnelle et moderne.

## 🚀 Accès à l'Interface

### Démarrage du Serveur

```bash
# 1. Activer l'environnement virtuel
source sothemalgo_env/bin/activate

# 2. Lancer le serveur moderne
python sothemalgo_web.py

# 3. Accéder à l'interface
# Ouvrir: http://localhost:5002
```

### Arrêt du Serveur
- **Ctrl + C** dans le terminal pour arrêter le serveur

## 🎯 Nouvelles Fonctionnalités

### 🏠 Page d'Accueil Moderne (`/`)
![Interface moderne](http://localhost:5002)

**Améliorations principales :**
- **Design professionnel** : Thème sombre moderne avec dégradés
- **Upload par Drag & Drop** : Glissez-déposez vos fichiers CSV
- **Tooltips informatifs** : Aide contextuelle sur tous les paramètres
- **Toggle données test** : Basculement facile entre données test et production
- **Validation temps réel** : Vérification instantanée des fichiers

**Utilisation :**
1. **Mode Test** : Activez le toggle "Données de test" pour une démo rapide
2. **Mode Production** : Uploadez vos fichiers CSV dans les zones dédiées
3. **Paramètres** : Ajustez horizon, taille de lot, fenêtre Premix
4. **Lancement** : Cliquez sur "Lancer l'analyse"

### 📊 Page de Résultats Moderne (`/results`)

**Fonctionnalités avancées :**
- **Statistiques visuelles** : Métriques clés en haut de page
- **Navigation par onglets** : Groupes / Non affectés / Résumé
- **Recherche en temps réel** : Filtrage instantané des données
- **Tables interactives** : Tri et navigation optimisés
- **Actions rapides** : Sidebar avec exports et visualisations

**Navigation :**
- **Onglet Groupes** : Voir tous les groupes générés
- **Onglet Non affectés** : OFs non assignés à un groupe
- **Onglet Résumé** : Vue d'ensemble et métriques

### 📈 Dashboard de Visualisation (`/data-visualization`)

**Graphiques avancés :**
- **Répartition en secteurs** : Distribution des groupes
- **Évolution temporelle** : Timeline des OFs
- **Efficacité par type** : Performance par catégorie
- **Analyse quantités** : Volume de production
- **Timeline détaillée** : Suivi des étapes

**Contrôles :**
- **Filtres temporels** : Semaine / Mois / Trimestre
- **Filtres par type** : PS / FG / Premix
- **Filtres par statut** : Affectés / Non affectés
- **Export** : Téléchargement des graphiques

## 🎨 Design System

### Palette de Couleurs
- **Primaire** : Bleu (#2563eb) - Actions principales
- **Accent** : Cyan (#06b6d4) - Éléments visuels
- **Succès** : Vert (#10b981) - États positifs
- **Attention** : Orange (#f59e0b) - Alertes
- **Erreur** : Rouge (#ef4444) - Erreurs

### Iconographie
- **Font Awesome 6** : Icônes modernes et cohérentes
- **Badges de statut** : Indicateurs visuels clairs
- **Loading spinners** : Feedback de traitement

## 📱 Responsive Design

### Compatibilité Multi-Écrans
- **Desktop** : Interface complète avec sidebar
- **Tablette** : Adaptation des grilles et navigation
- **Mobile** : Interface simplifiée et tactile

### Navigateurs Supportés
- ✅ **Chrome/Chromium** 90+
- ✅ **Firefox** 88+
- ✅ **Safari** 14+
- ✅ **Edge** 90+

## ⌨️ Raccourcis Clavier

### Navigation Rapide
- **Ctrl + F** : Recherche dans la page active
- **Échap** : Fermer les recherches/modales
- **Tab** : Navigation au clavier

### Actions Courantes
- **Entrée** : Valider les formulaires
- **Ctrl + R** : Actualiser les données

## 🔧 Configuration Avancée

### Paramètres d'Algorithme
- **Horizon de planification** : 1-52 semaines (défaut: 12)
- **Taille de lot maximum** : Production max par lot (défaut: 10000)
- **Fenêtre Premix** : 1-24 heures (défaut: 8)
- **Seuil de groupement** : 0-1 (défaut: 0.8)

### Format des Fichiers CSV
Les mêmes formats que l'ancienne interface :
- **Besoins** : besoins_non_lisse_x3.csv
- **Nomenclature** : nomenclature_multi_niveaux.csv
- **Postes** : postes_et_centres.csv
- **Opérations** : operations_et_gammes.csv
- **Indisponibilités** : indisponibilites_postes.csv

## 🚦 Indicateurs de Statut

### États des Fichiers
- 🟢 **Fichier valide** : CSV correctement formaté
- 🟡 **Attention** : Données manquantes non critiques
- 🔴 **Erreur** : Format invalide ou données manquantes

### États du Traitement
- ⏳ **En cours** : Algorithme en traitement
- ✅ **Terminé** : Résultats disponibles
- ❌ **Erreur** : Échec du traitement

## 🎯 Bonnes Pratiques

### Utilisation Optimale
1. **Commencer par les données test** pour se familiariser
2. **Vérifier les tooltips** pour comprendre chaque paramètre
3. **Utiliser la recherche** pour naviguer dans les résultats
4. **Exporter les résultats** pour les analyses externes

### Performance
- **Fichiers CSV** : Éviter les fichiers > 50MB
- **Navigateur** : Utiliser un navigateur récent
- **Résolution** : Minimum 1024x768 recommandé

## 🔗 Liens Rapides

### Navigation
- 🏠 **Accueil** : [http://localhost:5002/](http://localhost:5002/)
- 📊 **Résultats** : Accessible après une analyse
- 📈 **Visualisation** : [http://localhost:5002/data-visualization](http://localhost:5002/data-visualization)
- 🔍 **API Données** : [http://localhost:5002/api/visualization-data](http://localhost:5002/api/visualization-data)

### Actions Rapides
- 📁 **Fichier brut** : `/display-output`
- 📥 **Téléchargement** : Bouton dans l'en-tête
- 🔄 **Nouvelle analyse** : Bouton "Retour" ou logo

## 🆘 Dépannage

### Problèmes Courants

**🔴 Serveur ne démarre pas**
```bash
# Vérifier l'environnement virtuel
source sothemalgo_env/bin/activate
pip install flask waitress

# Relancer
python sothemalgo_web.py
```

**🔴 Page blanche/erreur 500**
- Vérifier les logs dans le terminal
- S'assurer que tous les templates modernes existent
- Redémarrer le serveur

**🔴 Upload de fichiers ne fonctionne pas**
- Vérifier le format CSV
- Taille < 50MB recommandée
- Vérifier les permissions du dossier `uploads/`

### Support
- **Logs** : Consultez la sortie du terminal
- **Templates** : Vérifiez que les `*_modern.html` existent
- **Navigateur** : F12 → Console pour les erreurs JavaScript

## 🎉 Conclusion

La nouvelle interface SothemaAL offre :
- ✅ **Expérience utilisateur moderne** et intuitive
- ✅ **Performance optimisée** avec animations fluides
- ✅ **Accessibilité** et navigation au clavier
- ✅ **Responsive** pour tous les écrans
- ✅ **API REST** pour l'intégration
- ✅ **Visualisations avancées** avec graphiques interactifs

**Prêt pour un usage industriel professionnel !** 🚀

---

*Pour plus d'informations techniques, consultez `WEB_OPTIMIZATION_REPORT.md`*
