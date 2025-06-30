# 📁 Guide des Fichiers de Données - Sothemalgo

## 🎯 Réponse à votre question

Quand vous cochez **"Utiliser les données de test intégrées"**, l'application utilise les fichiers **`test_*.csv`** (sans le suffixe `_client`).

## 📊 Structure des Fichiers de Données

### 🔧 Fichiers Utilisés par l'Application

| Option Interface | Fichiers Utilisés | Localisation |
|------------------|-------------------|--------------|
| ☑️ **"Utiliser les données de test"** | `test_*.csv` | Répertoire principal |
| ☐ **Données de production** | `*_multi_niveaux.csv`, `besoins_non_lisse_x3.csv` | Répertoire principal |
| 📁 **Fichiers uploadés** | Vos fichiers personnels | Dossier `uploads/` |

### 📁 Détail des Fichiers de Test

#### ✅ Fichiers Utilisés par l'Application
```
📁 /Users/abderrahman/Desktop/Sothemalgo2/
├── test_besoins.csv              ← 🎯 UTILISÉ si "données de test" cochée
├── test_nomenclature.csv         ← 🎯 UTILISÉ si "données de test" cochée  
├── test_operations.csv           ← 🎯 UTILISÉ si "données de test" cochée
├── test_posts.csv                ← 🎯 UTILISÉ si "données de test" cochée
└── test_post_unavailability.csv  ← 🎯 UTILISÉ si "données de test" cochée
```

#### 📋 Fichiers de Référence Client (NON utilisés par l'app)
```
📁 /Users/abderrahman/Desktop/Sothemalgo2/
├── test_besoins_client.csv       ← ❌ PAS utilisé par l'application
├── test_nomenclature_client.csv  ← ❌ PAS utilisé par l'application
├── test_operations_client.csv    ← ❌ PAS utilisé par l'application
└── test_posts_client.csv         ← ❌ PAS utilisé par l'application
```

#### 📁 Fichiers dans Uploads (utilisés si uploadés)
```
📁 /Users/abderrahman/Desktop/Sothemalgo2/uploads/
├── test_besoins_client.csv       ← Copies des fichiers client
├── test_nomenclature_client.csv  ← (utilisés uniquement si uploadés)
├── test_operations_client.csv    ← via l'interface web)
└── test_posts_client.csv         
```

## 🔄 Logique de Sélection des Fichiers

Voici comment l'application choisit les fichiers (dans l'ordre de priorité) :

### 1️⃣ Fichiers Uploadés (Priorité 1)
```javascript
SI (vous uploadez un fichier via l'interface)
→ Utilise votre fichier dans uploads/
```

### 2️⃣ Mode Test (Priorité 2) 
```javascript  
SI (☑️ "Utiliser les données de test intégrées" est cochée)
→ Utilise test_besoins.csv
→ Utilise test_nomenclature.csv  
→ Utilise test_operations.csv
→ Utilise test_posts.csv
→ Utilise test_post_unavailability.csv
```

### 3️⃣ Mode Production (Priorité 3)
```javascript
SI (☐ "Utiliser les données de test intégrées" est décochée)
→ Utilise besoins_non_lisse_x3.csv (→ lien vers test_besoins.csv)
→ Utilise nomenclature_multi_niveaux.csv (→ lien vers test_nomenclature.csv)
→ Utilise operations.csv (→ lien vers test_operations.csv)
→ Utilise posts.csv (→ lien vers test_posts.csv)
→ Utilise post_unavailability.csv (→ lien vers test_post_unavailability.csv)
```

## 🎯 Réponse Directe

**Question** : Les "données de test intégrées" utilisent-elles les fichiers `uploads/` ou `test_nomenclature_client` ?

**Réponse** : **AUCUN des deux !** 

Les "données de test intégrées" utilisent :
- ✅ `test_besoins.csv` (pas le `_client`)
- ✅ `test_nomenclature.csv` (pas le `_client`)  
- ✅ `test_operations.csv` (pas le `_client`)
- ✅ `test_posts.csv` (pas le `_client`)
- ✅ `test_post_unavailability.csv`

## 📋 Différences entre les Fichiers

### `test_*.csv` (Utilisés par l'app)
- 📊 **Contenu** : Données de test optimisées pour l'algorithme
- 🎯 **Usage** : Tests automatisés et démonstrations
- 📏 **Taille** : Plus complets (1346 lignes pour besoins)

### `test_*_client.csv` (Références)
- 📊 **Contenu** : Exemples client ou données réduites
- 🎯 **Usage** : Documentation et exemples
- 📏 **Taille** : Plus petits (1104 lignes pour besoins)

## 🚀 Recommandation

Pour tester l'application :
1. ☑️ **Cochez** "Utiliser les données de test intégrées"
2. 🚀 **Lancez** l'analyse  
3. ✅ L'app utilisera automatiquement les bons fichiers `test_*.csv`

Les fichiers `*_client.csv` sont juste des références, vous n'avez pas besoin de vous en préoccuper ! 😊
