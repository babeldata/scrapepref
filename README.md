# Scraper des arrêtés de la préfecture de police de Paris

Scraper automatisé pour extraire les arrêtés publiés sur le site de la préfecture de police de Paris, avec classification automatique des arrêtés de circulation.

## 🎯 Fonctionnalités

- ✅ Extraction automatique des arrêtés depuis le site de la préfecture de police
- ✅ Classification automatique des arrêtés de circulation (recherche du mot "circulation" dans le titre)
- ✅ Nettoyage automatique des données (séparation des arrêtés concaténés)
- ✅ Extraction précise du numéro d'arrêté, titre et date
- ✅ Téléchargement des PDFs
- ✅ Upload vers S3 (AWS S3 ou MinIO)
- ✅ Export CSV avec métadonnées complètes
- ✅ CSV séparé pour les arrêtés de circulation
- ✅ Automatisation via GitHub Actions
- ✅ Mode test (DRY_RUN) sans upload S3
- ✅ Support Firefox en fallback si Chromium ne fonctionne pas

## 📋 Prérequis

- **Python 3.11+**
- **uv** : Gestionnaire de paquets ultra-rapide (recommandé)
- **Playwright** : Navigateur headless pour JavaScript
- **Compte AWS S3** (ou MinIO) pour stocker les PDFs

## 🚀 Installation

### 1. Cloner le repository

```bash
git clone https://github.com/babeldata/scrapepref.git
cd scrapepref
```

### 2. Installer les dépendances

**Avec uv (recommandé)** :

```bash
# Installer uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Installer les dépendances Python
uv pip install -r requirements.txt

# Installer Playwright
playwright install chromium
```

**Avec pip classique** :

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurer les variables d'environnement

Copiez `env.example` vers `.env` et configurez :

```bash
cp env.example .env
```

Éditez `.env` avec vos credentials :

```env
# Configuration AWS S3
AWS_ACCESS_KEY_ID=your_access_key_here
AWS_SECRET_ACCESS_KEY=your_secret_key_here
AWS_REGION=us-east-1
S3_BUCKET_NAME=your_bucket_name_here

# Pour MinIO ou autre S3-compatible: spécifier l'URL
# Exemples: http://localhost:9000 ou https://minio.example.com
# Laisser vide pour AWS S3 standard
S3_ENDPOINT_URL=https://minio.example.com

# Configuration du scraper
SCRAPE_DELAY_SECONDS=2
MAX_CONCURRENT_PAGES=5
MAX_PAGES_TO_SCRAPE=0  # 0 = toutes les pages

# Mode test (sans upload S3)
DRY_RUN=false
```

### 4. Configurer GitHub Secrets (pour l'automatisation)

**Option A - Secrets au niveau du repository (recommandé pour débuter)** :

Dans votre repository GitHub, aller dans `Settings > Secrets and variables > Actions > Repository secrets` et ajouter :

* `AWS_ACCESS_KEY_ID`
* `AWS_SECRET_ACCESS_KEY`
* `AWS_REGION`
* `S3_BUCKET_NAME`
* `S3_ENDPOINT_URL` (laisser vide pour AWS S3, ou votre URL MinIO, ex: `https://minio.example.com`)

**Option B - Créer un Environment (recommandé pour la production)** :

1. Dans votre repository : `Settings > Environments > New environment`
2. Nommez-le `production`
3. Ajoutez les mêmes 5 secrets dans cet environment
4. Dans `.github/workflows/daily_scrape.yml`, décommentez la ligne `# environment: production`
5. (Optionnel) Configurez des protections : approbation manuelle, restrictions de branches, etc.

**Note pour MinIO** : Le scraper supporte nativement MinIO et autres services compatibles S3. Il suffit de spécifier votre endpoint dans `S3_ENDPOINT_URL`.

## 🧪 Test Local

Pour tester rapidement le scraper sur votre machine :

```bash
# En mode DRY_RUN (sans upload S3 - pas besoin de credentials)
export DRY_RUN=true
export MAX_PAGES_TO_SCRAPE=2  # Limiter à 2 pages
python run_local.py
```

Le script `run_local.py` :

* ✅ Vérifie la configuration
* ✅ Limite automatiquement à 2 pages en mode test
* ✅ Affiche des messages d'aide clairs
* ✅ Sauvegarde le HTML dans `data/debug_page_*.html` pour debug
* ✅ Génère le CSV avec les métadonnées

**Script de debug HTML** :

Pour analyser la structure HTML du site en détail :

```bash
python test_local.py
```

Ce script :

* Récupère la première page de résultats
* Sauvegarde le HTML dans `debug_local.html`
* Analyse les éléments HTML et recherche les patterns
* Affiche un rapport détaillé dans la console

## 💻 Utilisation

### Exécution manuelle

```bash
cd src
python scraper.py
```

### Mode test (DRY_RUN)

Pour tester le scraper sans uploader vers S3 :

```bash
export DRY_RUN=true
export MAX_PAGES_TO_SCRAPE=1  # Limiter à 1 page pour les tests
cd src
python scraper.py
```

Le mode DRY_RUN :

* Ne nécessite pas de credentials S3
* Simule l'upload des PDFs
* Enregistre quand même les métadonnées dans le CSV
* Affiche `[DRY_RUN]` dans les logs

### Exécution automatique

Le GitHub Action s'exécute automatiquement tous les jours à 6h du matin (heure de Paris).

### Test avec GitHub Actions (mode dry-run)

Pour tester le scraper sans uploader vers S3 :

1. Allez dans l'onglet **Actions** de votre repo GitHub
2. Sélectionnez **"Test Scraper (Dry Run)"** dans la liste des workflows
3. Cliquez sur **"Run workflow"**
4. Configurez les paramètres :  
   * **max_pages** : `1` (nombre de pages à scraper)  
   * **dry_run** : `true` (pas d'upload S3 réel)  
   * **max_concurrent** : `3` (pages en parallèle)
5. Cliquez sur **"Run workflow"** (bouton vert)

Le workflow va :

* ✅ Scraper 1 page de résultats
* ✅ Simuler l'upload des PDFs (pas d'upload réel)
* ✅ Afficher un résumé dans l'interface GitHub
* ✅ Uploader les logs et le CSV comme artefacts (téléchargeables pendant 7 jours)

### Lancement manuel du scraping complet

Vous pouvez aussi lancer manuellement le scraping complet depuis l'interface GitHub :

1. Aller dans l'onglet `Actions`
2. Sélectionner `Daily Scrape of Prefecture Arrêtés`
3. Cliquer sur `Run workflow`

### Rescraping des PDFs manquants (mise à jour des URLs S3)

Si certains arrêtés dans le CSV n'ont pas de lien S3, vous pouvez utiliser le workflow de rescraping pour télécharger et uploader les PDFs manquants :

**Depuis GitHub Actions** :

1. Aller dans l'onglet `Actions`
2. Sélectionner `Rescrape Missing S3 URLs`
3. Cliquer sur `Run workflow`
4. Configurer les paramètres :
   * **dry_run** : `false` (pour uploader réellement) ou `true` (pour tester)
   * **scrape_delay** : `2` (délai en secondes entre téléchargements)
5. Cliquer sur `Run workflow`

Le workflow va :
* ✅ Identifier les lignes du CSV `arretes_circulation.csv` sans `pdf_s3_url`
* ✅ Vérifier si les fichiers existent déjà sur S3
* ✅ Télécharger les PDFs manquants depuis les URLs originales
* ✅ Uploader les PDFs sur S3
* ✅ Mettre à jour le CSV avec les nouvelles URLs S3
* ✅ Commiter automatiquement les changements

**En local** :

```bash
python rescrape_missing_s3.py
```

Le script utilise les mêmes variables d'environnement que le scraper principal.

## 📁 Structure des données

### CSV (`data/arretes.csv`)

Colonnes :

* `numero_arrete` : Numéro unique de l'arrêté (format : 2025-01535)
* `titre` : Titre complet de l'arrêté (nettoyé, sans concaténation avec d'autres arrêtés)
* `date_publication` : Date de publication (format DD/MM/YYYY)
* `lien` : URL de la page de l'arrêté
* `pdf_url` : URL du PDF
* `is_circulation` : `True` si c'est un arrêté de circulation (contient "circulation" dans le titre), `False` sinon
* `contenu_preview` : Aperçu du contenu (200 premiers caractères, nettoyé)
* `pdf_s3_url` : URL S3 du PDF (`s3://bucket/arretes/2025/arrete_abc12345.pdf`)
* `poids_pdf_ko` : Taille du PDF en Ko
* `date_scrape` : Date et heure du scraping (ISO 8601)

### CSV Circulation (`data/arretes_circulation.csv`)

Fichier CSV séparé contenant uniquement les arrêtés de circulation (où `is_circulation == True`).

### S3

Les PDFs sont organisés par année :

```
s3://your-bucket/arretes/
├── 2025/
│   ├── arrete_abc12345.pdf
│   ├── arrete_def67890.pdf
│   └── ...
├── 2024/
│   └── ...
```

Le hash MD5 (8 premiers caractères) est ajouté au nom de fichier pour éviter les duplicatas.

## 🔍 Classification des arrêtés de circulation

Le scraper classe automatiquement les arrêtés selon qu'ils concernent la circulation ou non. 

**Méthode simple et efficace** : La classification se base uniquement sur la présence du mot **"circulation"** dans le titre de l'arrêté (insensible à la casse).

Un arrêté est classé comme arrêté de circulation si son titre contient le mot "circulation". Cette méthode simple garantit une précision élevée et évite les faux positifs.

## ⚙️ Configuration avancée

### Limiter le scraping

Pour tester ou limiter le nombre de pages scrapées :

```bash
export MAX_PAGES_TO_SCRAPE=5  # Scraper seulement les 5 premières pages
python src/scraper.py
```

### Ajuster la vitesse

Le site peut être lent. Les délais par défaut sont :

* `SCRAPE_DELAY_SECONDS=2` : Délai entre chaque requête
* `MAX_CONCURRENT_PAGES=5` : Nombre de pages ouvertes en parallèle

Vous pouvez augmenter ces valeurs si vous rencontrez des timeouts.

### Ajuster les timeouts

Si le site est très lent ou que vous rencontrez des timeouts, augmentez ces valeurs (en millisecondes) :

```bash
export PAGE_LOAD_TIMEOUT=120000  # 120 secondes pour charger une page (défaut: 90s)
export PDF_DOWNLOAD_TIMEOUT=90000  # 90 secondes pour télécharger un PDF (défaut: 60s)
```

Ces timeouts contrôlent combien de temps Playwright attend avant d'abandonner une opération.

### Personnaliser la classification

Pour modifier les critères de classification des arrêtés de circulation, éditez la fonction `is_circulation_arrete()` dans `src/scraper.py` :

```python
def is_circulation_arrete(titre: str, contenu: str = "") -> bool:
    """
    Détermine si un arrêté concerne la circulation.
    Simple : cherche le mot "circulation" dans le titre.
    """
    titre_lower = titre.lower()
    return 'circulation' in titre_lower
```

Vous pouvez modifier cette fonction pour ajouter d'autres critères si nécessaire (par exemple, chercher aussi "stationnement" ou d'autres mots-clés).

## 📊 Statistiques

Le scraper affiche des statistiques à la fin de l'exécution :

```
Statistiques:
  Total arrêtés: 150
  Arrêtés de circulation: 45
  Autres arrêtés: 105
```

**Note sur la classification** : Un arrêté est classé comme "circulation" si son titre contient le mot "circulation". Cette méthode simple garantit une précision élevée.

## 🐛 Problèmes connus

1. **Site lent** : Le site peut être très lent. Les timeouts sont configurés à 90 secondes par défaut.
2. **Téléchargement PDF** : Certains PDFs peuvent être inaccessibles (document retiré, erreur serveur). Dans ce cas, le scraper enregistre `ERROR: PDF non téléchargé` dans le CSV.
3. **Rate limiting** : Si trop de requêtes sont faites rapidement, le site peut bloquer temporairement. Ajustez `SCRAPE_DELAY_SECONDS`.
4. **Structure HTML** : La structure HTML du site peut changer. Utilisez `test_local.py` pour analyser la structure actuelle et adapter les sélecteurs dans `scraper.py`.
5. **Chromium sur macOS** : Si Chromium crash, le scraper essaie automatiquement Firefox en fallback.

## 🔧 Dépendances

* **Python 3.11+**
* **uv** : Gestionnaire de paquets ultra-rapide (recommandé)
* **Playwright** : Navigateur headless pour JavaScript
* **BeautifulSoup4** : Parsing HTML
* **Pandas** : Gestion CSV
* **Boto3** : Upload S3
* **python-dotenv** : Variables d'environnement
* **lxml** : Parser XML/HTML rapide

## 📝 Licence

Ce projet est sous licence MIT.

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

## ⚠️ Avertissement

Ce scraper est conçu pour un usage éducatif et de recherche. Assurez-vous de respecter les conditions d'utilisation du site de la préfecture de police et les lois en vigueur concernant le scraping de données publiques.

## 📚 Ressources

- [Site de la préfecture de police](https://www.prefecturedepolice.interieur.gouv.fr/actualites-et-presse/arretes/accueil-arretes)
- [Documentation Playwright](https://playwright.dev/python/)
- [Documentation Boto3 (S3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

