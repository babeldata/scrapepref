# Guide de contribution

Merci de votre intérêt pour contribuer à ce projet ! Ce document fournit des directives pour contribuer au scraper des arrêtés de la préfecture de police.

## 🚀 Démarrage rapide

1. Fork le repository
2. Clone votre fork : `git clone https://github.com/votre-username/scrapepref.git`
3. Créez une branche : `git checkout -b feature/ma-fonctionnalite`
4. Installez les dépendances : `uv pip install -r requirements.txt && playwright install chromium`
5. Testez vos modifications : `python run_local.py`

## 📝 Processus de contribution

### 1. Signaler un bug

Si vous trouvez un bug, ouvrez une issue avec :
- Description claire du problème
- Étapes pour reproduire
- Comportement attendu vs comportement actuel
- Version de Python et OS
- Logs pertinents (si disponibles)

### 2. Proposer une amélioration

Pour proposer une nouvelle fonctionnalité :
- Ouvrez une issue pour discuter de l'idée
- Décrivez le cas d'usage et les bénéfices
- Attendez la validation avant de coder

### 3. Soumettre une Pull Request

1. **Assurez-vous que votre code fonctionne** :
   ```bash
   python run_local.py  # Test en mode DRY_RUN
   ```

2. **Suivez les conventions de code** :
   - Utilisez des noms de variables explicites
   - Ajoutez des docstrings aux fonctions
   - Commentez les parties complexes
   - Respectez PEP 8 (formatage Python)

3. **Testez vos modifications** :
   - Vérifiez que le scraper fonctionne avec `run_local.py`
   - Testez la classification des arrêtés
   - Vérifiez l'upload S3 (en mode DRY_RUN)

4. **Documentez vos changements** :
   - Mettez à jour le README si nécessaire
   - Ajoutez des commentaires dans le code
   - Documentez les nouvelles variables d'environnement

5. **Soumettez la PR** :
   - Titre clair et descriptif
   - Description détaillée des changements
   - Référencez les issues liées (ex: "Fixes #123")

## 🔍 Zones de contribution

### Amélioration de la classification

La fonction `is_circulation_arrete()` dans `src/scraper.py` peut être améliorée :
- Ajouter de nouveaux mots-clés
- Améliorer les patterns regex
- Utiliser du NLP pour une meilleure précision

### Extraction de données

La fonction `extract_arrete_info()` peut être adaptée si la structure HTML du site change :
- Adapter les sélecteurs CSS
- Extraire de nouvelles métadonnées
- Gérer de nouveaux formats de dates

### Performance

Optimisations possibles :
- Parallélisation améliorée
- Cache des pages déjà scrapées
- Gestion plus efficace de la mémoire

### Tests

Ajout de tests unitaires et d'intégration :
- Tests de classification
- Tests d'extraction HTML
- Tests d'upload S3 (mock)

## 📋 Checklist avant de soumettre

- [ ] Code testé localement
- [ ] Pas d'erreurs de linting
- [ ] Documentation mise à jour
- [ ] Variables d'environnement documentées
- [ ] Messages de commit clairs
- [ ] PR liée à une issue (si applicable)

## 🎯 Priorités actuelles

1. **Amélioration de la classification** : Réduire les faux positifs/négatifs
2. **Robustesse** : Gérer les changements de structure HTML
3. **Performance** : Optimiser le temps de scraping
4. **Tests** : Ajouter une suite de tests complète

## 💬 Questions ?

N'hésitez pas à ouvrir une issue pour poser des questions ou discuter d'idées avant de commencer à coder !

