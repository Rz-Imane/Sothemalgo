# 🏭 Sothemalgo - Algorithme de Groupement et Planification

**Sothemalgo** est un **algorithme intelligent de planification industrielle** qui résout un problème complexe : **Comment organiser efficacement la production dans une usine ?**

Interface web moderne pour l'algorithme de groupement et planification des ordres de fabrication Sothemalgo.

## ✨ Fonctionnalités

- 🎯 **Algorithme de groupement multiniveau** : Regroupement intelligent des ordres de fabrication (OF) en tenant compte de la nomenclature complète (PS, SF, PF).
- 📦 **Gestion des stocks par composant** : Suivi précis des stocks pour chaque article (PS, SF1, SF2, etc.) au sein des groupes.
- 📅 **Lissage et planification** : Optimisation temporelle avec contraintes de capacité des postes, horaires de travail et indisponibilités.
- 🌐 **Interface web moderne** : Interface responsive avec drag & drop pour le téléversement des fichiers.
- 📊 **Visualisation interactive** : Graphiques et statistiques pour analyser les résultats.
- 🔧 **Paramètres configurables** : Horizon de regroupement, semaines de recul, et mode automatique.

## 🚀 Démarrage rapide

### 💻 Installation

#### Pour les utilisateurs Unix/Linux/Mac :
```bash
# Activer l'environnement virtuel
source sothemalgo_env/bin/activate

# Option 1: Installer toutes les dépendances (recommandé)
pip install -r requirements.txt

# Option 2: Installation minimale (plus rapide)
pip install -r requirements-minimal.txt
```

#### 🪟 Pour les utilisateurs Windows :

> ⚠️ **Important pour les entreprises** : Si vous avez des problèmes de permissions avec cmd ou PowerShell, utilisez **Git Bash** (recommandé en entreprise).
>
> 📖 **Guide détaillé** : Voir [WINDOWS_ENTREPRISE.md](WINDOWS_ENTREPRISE.md) pour les instructions complètes Git Bash en environnement d'entreprise.

**Option A - Git Bash (recommandé en entreprise) :**

```bash
# Ouvrir Git Bash
# Naviguer vers le dossier du projet
cd /c/chemin/vers/Sothemalgo2

# Activer l'environnement virtuel (syntaxe Unix dans Git Bash)
source sothemalgo_env/Scripts/activate

# Option 1: Installer toutes les dépendances (recommandé)
pip install -r requirements.txt

# Option 2: Installation minimale (plus rapide)
pip install -r requirements-minimal.txt
```

**Option B - CMD/PowerShell (si autorisé) :**

```cmd
# Ouvrir l'invite de commande (cmd) ou PowerShell
# Naviguer vers le dossier du projet
cd C:\chemin\vers\Sothemalgo2

# Activer l'environnement virtuel Windows
sothemalgo_env\Scripts\activate

# Option 1: Installer toutes les dépendances (recommandé)
pip install -r requirements.txt

# Option 2: Installation minimale (plus rapide)
pip install -r requirements-minimal.txt
```

> 💡 **Astuce** : Pour voir toutes les options d'installation disponibles, utilisez :
>
> ```bash
> ./show_dependencies.sh  # Unix/Linux/Mac
> ```

### 🚀 Lancement

#### Pour les utilisateurs Unix/Linux/Mac :
```bash
# Méthode 1: Script de démarrage (recommandé)
./start_web.sh

# Méthode 2: Menu interactif
./start_quick.sh

# Méthode 3: Manuellement
source sothemalgo_env/bin/activate && python sothemalgo_web.py
```

#### 🪟 Pour les utilisateurs Windows :

> ⚠️ **Important pour les entreprises** : Si vous avez des problèmes de permissions avec cmd ou PowerShell, utilisez **Git Bash** (recommandé en entreprise).

**Option A - Git Bash (recommandé en entreprise) :**
```bash
# Lancement avec Git Bash - Syntaxe Unix
source sothemalgo_env/Scripts/activate
python sothemalgo_web.py

# Test de l'algorithme
source sothemalgo_env/Scripts/activate
python test_new_algo.py

# Vérification du projet
bash verify_project.sh
```

**Option B - CMD/PowerShell (si autorisé) :**
```cmd
# Méthode 1: Activation et lancement manuel
sothemalgo_env\Scripts\activate
python sothemalgo_web.py

# Méthode 2: Test de l'algorithme
sothemalgo_env\Scripts\activate
python test_new_algo.py

# Méthode 3: Vérification du projet (avec Git Bash ou WSL)
bash verify_project.sh
```

### 🌐 Accès
- **Interface principale** : [http://127.0.0.1:5002/](http://127.0.0.1:5002/)

---

## 🎯 COMPRENDRE SOTHEMALGO DE ZÉRO À HÉROS

### 🏭 **Le Problème Résolu**

Imaginez une usine qui fabrique des produits électroniques :
- Vous avez des **commandes clients** (PF001, PF002, etc.)
- Chaque produit est composé de **sous-ensembles** (SF001, SF002)
- Chaque sous-ensemble nécessite des **composants de base** (PS001, PS002)
- Vous avez des **machines limitées** et des **contraintes de temps**

**❓ Question :** Comment grouper et planifier toute cette production pour être le plus efficace possible ?

**✅ Réponse :** **SOTHEMALGO !**

### 🔧 **Comment ça marche ? (Simplifié)**

#### **Étape 1 : Je reçois les données**
L'algorithme lit 5 fichiers Excel/CSV :

1. **`test_besoins.csv`** = "Qu'est-ce qu'on doit fabriquer et quand ?"
   ```
   PF001 (BATENS PREMIUM) → 50 unités pour le 15 juin
   SF001 (Sous-ensemble)   → 100 unités pour le 20 juin
   PS001 (Processeur)      → 200 unités pour le 25 juin
   ```

2. **`test_nomenclature.csv`** = "De quoi est fait chaque produit ?"
   ```
   PF001 = 2 × SF001 + 1 × SF002 + 1 × PS001
   SF001 = 1 × PS001 + 1 × PS002 + 1 × PS003
   ```

3. **`test_operations.csv`** = "Comment fabriquer (gammes) ?"
   ```
   PF001 → Assemblage (2.5h) → Test (1h) → Contrôle (0.5h) → Emballage (0.3h)
   ```

4. **`test_posts.csv`** = "Quelles machines disponibles ?"
   ```
   ASSY01 (Poste d'assemblage) - Capacité 35h/semaine
   TEST01 (Poste de test)      - Capacité 30h/semaine
   ```

5. **`test_post_unavailability.csv`** = "Quand les machines sont-elles en panne ?"

#### **Étape 2 : Je groupe intelligemment**

L'algorithme **regroupe** les ordres de fabrication qui peuvent être faits ensemble :

```
🎯 GROUPE 1 (Semaine du 24 juin)
   ├── PF001 (50 unités) ← Commande client
   ├── SF001 (100 unités) ← Besoin calculé
   ├── PS001 (200 unités) ← Composant nécessaire
   ├── PS002 (300 unités) ← Composant nécessaire
   └── PS003 (250 unités) ← Composant nécessaire

🎯 GROUPE 2 (Semaine du 1er juillet)
   ├── PF002 (75 unités)
   └── SF002 (150 unités)
```

#### **Étape 3 : Je planifie dans le temps**

Pour chaque groupe, l'algorithme planifie **QUAND** et **SUR QUELLE MACHINE** faire chaque opération :

```
📅 24 juin 2024
  08h00-10h30 : PF001 Assemblage sur ASSY01
  10h30-11h30 : PF001 Test sur TEST01
  11h30-12h00 : PF001 Contrôle sur CTRL01
  13h00-13h18 : PF001 Emballage sur PACK01
```

#### **Étape 4 : Je génère le planning final**

Le résultat est un fichier détaillé qui montre :
- **Quoi fabriquer**
- **Quand le faire**
- **Sur quelle machine**
- **Combien de stock il reste**

### 🎭 **Les 3 types d'objets (Très Important !)**

**Sothemalgo** gère 3 niveaux de produits :

#### 🔹 **PS (Produits Semi-finis)**
- **Exemples :** Processeur, Capteur, Régulateur
- **Analogie :** Les "briques LEGO" de base
- **Niveau :** 0 (le plus bas dans la nomenclature)

#### 🔹 **SF (Sous-ensembles Finis)**
- **Exemples :** Carte électronique, Module WiFi
- **Analogie :** Des "assemblages de briques LEGO"
- **Niveau :** 1 ou 2 (intermédiaire)

#### 🔹 **PF (Produits Finis)**
- **Exemples :** BATENS PREMIUM, BATENS STANDARD
- **Analogie :** Le "château LEGO" final
- **Niveau :** 3 (le plus haut, pour le client)

### 🧠 **La logique intelligente**

#### **Pourquoi grouper ?**
Au lieu de fabriquer ordre par ordre, l'algorithme **groupe** pour :
- ✅ **Optimiser l'utilisation des machines**
- ✅ **Réduire les changements de série**
- ✅ **Lisser la charge de travail**
- ✅ **Respecter les délais clients**

#### **Comment ça marche concrètement ?**

1. **Je commence par les besoins CLIENTS** (PF/SF)
2. **Je calcule TOUT ce qu'il faut en composants** (via la nomenclature)
3. **Je cherche les PS disponibles dans la même période**
4. **Je vérifie qu'on a assez de stock pour tout faire**
5. **Je planifie dans l'ordre optimal sur les machines**

### 📊 **Exemple concret de résultat**

Quand vous lancez l'algorithme, vous obtenez quelque chose comme ça :

```
# Group ID: GRP1
#   Produit PS Principal: PS002
#   Fenêtre Temporelle: 24/06/2024 à 21/07/2024
#   Stock PF001 Restant: 50.00
#   Stock SF001 Restant: -100.00  ← ⚠️ En déficit !
#   Stock PS001 Restant: 800.00
#   Stock PS002 Restant: 800.00
#   OFs dans ce Groupe:
PF001	BATENS PREMIUM	OF240601	A	3	1	1	50	15/06/2024	1	24/06/2024	9
PS001	Processeur Central	OF240605	E	0	1	1	200	25/06/2024	1	24/06/2024	0
```

**Lecture :** 
- Le groupe 1 contient PF001 et PS001
- Il y a un stock positif de PS001 (800 unités)
- ⚠️ Il manque 100 unités de SF001 (stock négatif)
- Tout est planifié à partir du 24 juin

### 🚀 **Pourquoi c'est révolutionnaire ?**

#### **Avant Sothemalgo :**
- ❌ Planification manuelle et laborieuse
- ❌ Oublis de composants
- ❌ Machines sous-utilisées
- ❌ Retards clients fréquents

#### **Avec Sothemalgo :**
- ✅ **Automatisation complète** de la planification
- ✅ **Vision globale** de tous les besoins
- ✅ **Optimisation** de l'utilisation des ressources
- ✅ **Alertes** en cas de problème de stock
- ✅ **Interface web moderne** pour les utilisateurs

### 🎯 **En résumé : Sothemalgo en 3 phrases**

1. **📋 Je lis vos commandes et votre nomenclature**
2. **🧠 Je groupe intelligemment et je planifie sur vos machines**  
3. **📊 Je vous donne un planning détaillé avec toutes les alertes**

**C'est comme avoir un chef d'atelier ultra-intelligent qui ne se trompe jamais et travaille 24h/24 !** 🤖✨

---

## ⚙️ Fonctionnement détaillé de l'algorithme

L'algorithme a pour but de regrouper les ordres de fabrication (OF) de manière optimale pour lisser la charge de production, tout en respectant les contraintes de la nomenclature et des capacités de production.

### Phase 1 : Chargement et Préparation des Données

L'algorithme commence par charger et structurer les données à partir de plusieurs fichiers d'entrée :
1.  **Besoins (`test_besoins.csv`)** : Contient la liste de tous les OFs (PF, SF, PS) avec leurs quantités et dates de besoin.
2.  **Nomenclature (`test_nomenclature.csv`)** : Définit les liens de parenté et les quantités nécessaires entre les différents niveaux de produits (un PF est composé de plusieurs SF, qui sont eux-mêmes composés de PS).
3.  **Postes (`test_posts.csv`)** : Liste les postes de travail disponibles.
4.  **Opérations (`test_operations.csv`)** : Décrit les gammes de fabrication, en associant chaque produit à des opérations sur des postes spécifiques avec des temps standards.
5.  **Indisponibilités (`post_unavailability.csv`)** : Spécifie les périodes de fermeture ou de maintenance des postes.

### Phase 2 : Algorithme de Groupement Intelligent (Multi-niveau)

C'est le cœur du processus. L'algorithme suit une logique itérative pour former des groupes de production cohérents.

**🎯 Nouvelle Approche (Option B) : Groupement basé sur les besoins clients (PF/SF)**

L'algorithme a été amélioré pour partir des besoins clients (PF/SF) plutôt que des produits semi-finis (PS) :

1.  **Initialisation** : Le processus commence par trier tous les OFs de type **PF/SF (besoins clients)** qui n'ont pas encore été assignés à un groupe. Le tri est basé sur le niveau de nomenclature décroissant, puis la date de besoin.

2.  **Création d'un Groupe basé sur le besoin client** : Un nouveau groupe est créé à partir du premier OF de PF/SF de la liste.
    - La **fenêtre temporelle** du groupe est définie à partir de la date de besoin du PF/SF et s'étend sur la durée de l'horizon de regroupement.
    - L'algorithme **calcule automatiquement tous les composants nécessaires** (PS, SF1, SF2, etc.) via la nomenclature.
    - Le **PS principal** est identifié comme celui requis en plus grande quantité.

3.  **Calcul des besoins multiniveau** : Pour chaque OF client (PF/SF), l'algorithme :
    - Parcourt récursivement la nomenclature pour identifier **tous les composants** nécessaires.
    - Calcule les **quantités exactes** de chaque composant (PS, SF1, SF2, etc.).
    - Initialise les stocks négatifs représentant les besoins à satisfaire.

4.  **Collecte des OFs PS disponibles** : L'algorithme recherche tous les OFs PS disponibles dans la fenêtre temporelle du groupe et les ajoute s'ils correspondent aux composants nécessaires.

5.  **Intégration d'autres besoins clients compatibles** : L'algorithme tente d'ajouter d'autres OFs PF/SF dans la même fenêtre temporelle, en vérifiant que tous leurs composants sont disponibles en stock.

6.  **Gestion multiniveau des stocks** : 
    - **Suivi par composant** : Chaque groupe maintient un dictionnaire `component_stocks` avec le stock de chaque article (PS001, SF001, etc.).
    - **Décrémentation automatique** : Lors de l'affectation d'un OF, les stocks de tous ses composants sont automatiquement décrémentés.
    - **Vérification de cohérence** : Aucun OF n'est affecté si un seul de ses composants manque.

7.  **Répétition** : Le processus continue jusqu'à ce que tous les OFs PF/SF aient été traités ou ne puissent plus être affectés.

### Phase 3 : Lissage et Planification Détaillée

Une fois les groupes formés, l'algorithme planifie chaque opération de chaque OF :
- Il respecte la **capacité des postes**, les **horaires de travail**, les **temps de pause** et les **périodes d'indisponibilité**.
- Il calcule une date de début et de fin au plus tôt pour chaque OF, en s'assurant que les ressources sont disponibles.

### Phase 4 : Génération du Fichier de Sortie

Le résultat final est écrit dans le fichier `test_besoins_groupes_output.txt`. Ce fichier contient :
- La liste de tous les OFs, regroupés visuellement.
- Pour chaque groupe, un **en-tête détaillé** indiquant :
    - Le produit PS principal du groupe.
    - La fenêtre temporelle.
    - Le **stock restant pour chaque composant** (PS, SF1, SF2...) à l'intérieur de ce groupe.
- À la fin du fichier, un **résumé global** des stocks restants pour tous les composants et des **alertes** en cas de stocks négatifs, offrant une visibilité complète sur la planification.

## 📁 Structure du projet (après nettoyage)

```text
sothemalgo2/
├── 📄 README.md                    # Documentation principale complète
├── 📄 CLEANUP_REPORT.md           # Rapport de nettoyage du projet
├── 🐍 sothemalgo_grouper.py        # Algorithme principal multiniveau
├── 🌐 sothemalgo_web.py            # Serveur web Flask (prêt production)
├── ⚙️ config.py                    # Configuration centralisée
├── � web_utils.py                 # Utilitaires web
├── �🚀 start_web.sh                 # Script de démarrage web
├── 🎯 start_quick.sh               # Menu interactif de démarrage
├── 🔍 verify_project.sh            # Script de vérification automatique
├── 📋 requirements.txt             # Dépendances Python complètes
├── 📋 requirements-minimal.txt     # Dépendances minimales (installation rapide)
├── 🧪 test_new_algo.py             # Script de test automatisé
├── 🗂️ .gitignore                   # Configuration Git optimisée
├── 📊 Données de test/
│   ├── test_besoins.csv            # Besoins de test
│   ├── test_besoins_client.csv     # Besoins clients de test
│   ├── test_nomenclature.csv       # Nomenclature de test
│   ├── test_nomenclature_client.csv # Nomenclature client de test
│   ├── test_posts.csv              # Postes de test
│   ├── test_posts_client.csv       # Postes clients de test
│   ├── test_operations.csv         # Opérations de test
│   ├── test_operations_client.csv  # Opérations client de test
│   └── test_post_unavailability.csv # Indisponibilités de test
├── 🎨 templates/
│   ├── index.html                  # Page d'accueil
│   ├── index_new.html              # Page d'accueil moderne
│   ├── results.html                # Page résultats
│   ├── display_output.html         # Affichage des sorties
│   ├── data_visualization.html     # Visualisation interactive
│   └── data_visualization_api.html # API de visualisation
├── 📁 static/
│   └── favicon.ico                 # Icône du site
├── 📁 uploads/                     # Fichiers uploadés par les utilisateurs
├── 🐍 sothemalgo_env/             # Environnement virtuel Python
└── 🗃️ .git/                       # Historique Git
```

**Note :** Le projet a été entièrement nettoyé ! Plus de fichiers obsolètes, de documentation redondante, ou de code inutilisé. Structure claire et maintenable.

## 🎯 Guide d'utilisation

### 1. Page d'accueil
- **Zone de téléchargement** : 5 sections pour vos fichiers (optionnel)
- **Paramètres** :
  - 📅 Semaines de recul (0-52)
  - 🤖 Mode automatique (Activé/Désactivé)
  - 🎯 Horizon temporel (1-12 semaines)
- **Options** : Données de test vs données par défaut

### 2. Algorithme Sothemalgo - Architecture Complète

#### 📚 **Concepts de base**

L'algorithme traite trois types d'ordres de fabrication (OF) :
- **PS (Produits Semi-finis)** : Matières premières transformées, niveau nomenclature élevé
- **SF (Sous-ensembles Finis)** : Composants assemblés à partir de PS
- **PF (Produits Finis)** : Produits finaux destinés aux clients

#### 🔄 **Phase 1 : Groupement Intelligent**

L'algorithme principal suit ces **7 étapes critiques** :

1. **📋 Tri et Priorisation des OF**
   ```
   Critères : (Désignation, -Niveau_BOM, Date_Besoin)
   ```
   - Classe les ordres par famille de produits
   - Priorise les niveaux nomenclature élevés (PS d'abord)
   - Respecte les échéances chronologiques

2. **⏰ Création des Fenêtres Temporelles**
   ```
   Fenêtre = [Lundi_semaine_besoin, Lundi + Horizon_semaines]
   ```
   - Arrondit au lundi pour standardiser
   - Horizon configurable (défaut : 4 semaines)
   - Optimise la planification par périodes fixes

3. **🎯 Sélection de l'OF PS de Référence**
   ```
   OF_base = Premier OF PS non-assigné (après tri)
   ```
   - Crée un nouveau groupe avec l'OF PS prioritaire
   - Génère un ID groupe unique (GRP1, GRP2, etc.)
   - Initialise le stock PS théorique disponible

4. **🔗 Ajout des OF PS Identiques**
   ```
   Si (Produit_ID identique && Type = PS && Date ∈ Fenêtre) :
       Ajouter_au_groupe()
       Stock_PS += Quantité_OF
   ```
   - Regroupe tous les PS du même produit dans la fenêtre
   - Cumule les quantités pour calculer le stock disponible

5. **📊 Calcul du Stock PS Théorique**
   ```
   Stock_disponible = Σ(Quantités_PS_du_groupe)
   ```
   - Somme toutes les quantités PS du groupe
   - Détermine la capacité de production pour les OF aval

6. **⬇️ Intégration des OF Aval (SF/PF)**
   ```
   Pour chaque OF ∈ {SF, PF} non-assigné :
       Besoin_PS = Quantité_nomenclature × Quantité_OF
       Si (Besoin_PS ≤ Stock_disponible && Date ≤ Fin_fenêtre) :
           Ajouter_au_groupe()
           Stock_disponible -= Besoin_PS
   ```
   - Vérifie la disponibilité des composants PS
   - Respecte les contraintes de nomenclature (BOM)
   - Maintient la cohérence des stocks

7. **🔄 Boucle de Groupement**
   ```
   Répéter tant qu'il existe des OF PS non-assignés
   ```
   - Continue jusqu'à épuisement des OF PS disponibles
   - Garantit que tous les OF sont traités

#### ⚡ **Phase 2 : Lissage et Planification**

Cette phase optimise la planification temporelle :

**🏗️ Gestion des Ressources**
- **Postes de travail** : Capacités, horaires, indisponibilités
- **Opérations** : Séquences, durées, priorités
- **Contraintes temporelles** : Fenêtres d'avance/retard

**📅 Algorithme de Planification**
```
Pour chaque Groupe (trié par date_début) :
    Pour chaque OF du groupe (PS d'abord, puis par date_besoin) :
        1. Charger les opérations nécessaires
        2. Définir la fenêtre de planification autorisée
        3. Planifier chaque opération en séquence :
           - Rechercher un créneau disponible sur le poste
           - Respecter la continuité (fin_op_i = début_op_i+1)
           - Vérifier les contraintes de capacité
        4. Mettre à jour le statut (PLANNED/FAILED_PLANNING)
```

**🎯 Contraintes Respectées**
- **R1 - Capacité** : Respect des charges maximales des postes
- **R2 - Priorité** : Ordre de traitement optimisé
- **R3 - Continuité** : Enchaînement fluide des opérations
- **R4 - Optimisation** : Minimisation des retards et avances

#### 📤 **Phase 3 : Génération des Résultats**

**📋 Format de Sortie Standardisé**
```
Part | Description | Order Code | FG | CAT | US | FS | Qty | X3 Date | GRP_FLG | Start Date | Delay
```

**📊 Statuts des OF**
- **PLANNED** : Planifié avec succès dans les contraintes
- **PLANNED_OUTSIDE_WINDOW** : Planifié hors fenêtre autorisée  
- **FAILED_PLANNING** : Échec de planification (ressources insuffisantes)
- **FAILED_PLANNING_NO_OPS** : Aucune opération définie
- **UNASSIGNED** : Non affecté à un groupe

**🎨 Informations par Groupe**
- ID du groupe et produit PS principal
- Fenêtre temporelle de production
- Stock PS théorique restant
- Liste des OF inclus avec planification détaillée

### 3. Visualisation
- **Statistiques temps réel** : Groupes, OFs, efficacité
- **Graphiques interactifs** : Distribution, performance, timeline
- **API REST** : Données JSON pour intégrations

## 🔧 Configuration

### Paramètres par défaut
- **Port serveur** : 5002
- **Horizon** : 4 semaines
- **Avance/Retard** : 3 semaines
- **Capacité posts** : 35h/semaine

### Fichiers supportés
- **Format** : CSV avec délimiteur `;`
- **Encodage** : UTF-8
- **Taille max** : 16MB

## 🪟 Guide spécial Windows

### 📋 Prérequis Windows
1. **Python 3.8+** installé depuis [python.org](https://python.org)
2. **Git pour Windows** (optionnel) pour cloner le projet
3. **Éditeur de texte** comme Notepad++ ou Visual Studio Code

### 🚀 Installation étape par étape Windows

> ⚠️ **Recommandation pour les entreprises** : En cas de restrictions de permissions sur cmd/PowerShell, utilisez **Git Bash** (méthode 1).

#### Méthode 1 : Avec Git Bash (recommandé en entreprise)
```bash
# 1. Installer Git pour Windows (si pas déjà fait) depuis git-scm.com
# 2. Ouvrir Git Bash (clic droit dans le dossier -> "Git Bash Here")
# 3. Naviguer vers le dossier du projet
cd /c/Users/VotreNom/Desktop/Sothemalgo2

# 4. Créer un environnement virtuel (si pas encore fait)
python -m venv sothemalgo_env

# 5. Activer l'environnement virtuel (syntaxe Unix dans Git Bash)
source sothemalgo_env/Scripts/activate

# 6. Installer les dépendances depuis requirements.txt
pip install -r requirements.txt

# Ou pour une installation minimale plus rapide :
# pip install -r requirements-minimal.txt

# 7. Lancer l'application
python sothemalgo_web.py
```

#### Méthode 2 : Avec l'invite de commande (cmd) - si autorisé
```cmd
# 1. Ouvrir l'invite de commande en tant qu'administrateur
# 2. Naviguer vers le dossier du projet
cd C:\Users\VotreNom\Desktop\Sothemalgo2

# 3. Créer un environnement virtuel (si pas encore fait)
python -m venv sothemalgo_env

# 4. Activer l'environnement virtuel
sothemalgo_env\Scripts\activate

# 5. Installer les dépendances depuis requirements.txt
pip install -r requirements.txt

# Ou pour une installation minimale plus rapide :
# pip install -r requirements-minimal.txt

# 6. Lancer l'application
python sothemalgo_web.py
```

#### Méthode 3 : Avec PowerShell - si autorisé
```powershell
# 1. Ouvrir PowerShell en tant qu'administrateur
# 2. Autoriser l'exécution de scripts (une seule fois)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. Naviguer vers le projet
cd C:\Users\VotreNom\Desktop\Sothemalgo2

# 4. Activer l'environnement virtuel
sothemalgo_env\Scripts\Activate.ps1

# 5. Lancer l'application
python sothemalgo_web.py
```

### 🛠️ Résolution de problèmes Windows

#### ❌ Problème : Restrictions de permissions en entreprise
**Solution :** Utilisez **Git Bash** au lieu de cmd/PowerShell
```bash
# 1. Installer Git pour Windows depuis git-scm.com
# 2. Clic droit dans le dossier du projet → "Git Bash Here"
# 3. Utiliser les commandes Unix standard :
source sothemalgo_env/Scripts/activate
python sothemalgo_web.py
```
**Avantages :** Git Bash contourne la plupart des restrictions d'entreprise car il émule un environnement Unix.

#### ❌ Problème : "python n'est pas reconnu"
**Solution :**
1. Réinstaller Python depuis [python.org](https://python.org)
2. ✅ Cocher "Add Python to PATH" pendant l'installation
3. Redémarrer l'invite de commande

#### ❌ Problème : "Scripts\activate.bat n'existe pas"
**Solution :**
```cmd
# Recréer l'environnement virtuel
rmdir /s sothemalgo_env
python -m venv sothemalgo_env
```

#### ❌ Problème : "Execution Policy Error" sur PowerShell
**Solution :**
```powershell
# Autoriser les scripts locaux
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### � Raccourcis Windows pratiques

#### Créer un fichier .bat pour lancer facilement :
Créez `lancer_sothemalgo.bat` :
```batch
@echo off
cd /d "C:\chemin\vers\Sothemalgo2"
call sothemalgo_env\Scripts\activate
python sothemalgo_web.py
pause
```

#### Créer un raccourci bureau :
1. Clic droit sur le bureau → Nouveau → Raccourci
2. Cible : `C:\chemin\vers\Sothemalgo2\lancer_sothemalgo.bat`
3. Nom : "Sothemalgo"

### 🌐 Accès depuis Windows
- **Interface web** : Ouvrir votre navigateur sur `http://localhost:5002`
- **Compatible** : Chrome, Firefox, Edge, Safari
- **Recommandé** : Chrome ou Firefox pour la meilleure expérience

## �📞 Support

Pour toute question ou problème :

### 📧 Support technique
1. Vérifiez que le serveur fonctionne sur le port 5002
2. Consultez les logs dans la console
3. Testez avec les données d'exemple incluses
4. Utilisez le script de vérification : `./verify_project.sh` (Unix) ou Git Bash (Windows)

### 🐛 Résolution de problèmes courants
- **Port occupé** : Modifier le port dans `config.py`
- **Fichiers introuvables** : Vérifier les chemins dans `config.py`
- **Erreurs de permissions** : Lancer en tant qu'administrateur
- **Problèmes d'affichage** : Vider le cache du navigateur

### 🔍 Tests et validation
```bash
# Test complet de l'algorithme
python test_new_algo.py

# Vérification de l'installation
python -c "import sothemalgo_grouper; print('✅ Installation OK')"

# Test de l'interface web
# Aller sur http://localhost:5002 et utiliser les données de test
```

---

*Version 2.0 - Juin 2025*
*Algorithme conforme aux spécifications industrielles*
