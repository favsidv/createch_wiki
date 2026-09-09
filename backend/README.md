# Wiki backend

## Lancement

Depuis backend/ :

```bash
uv sync --frozen
uv run fastapi dev
```

Le serveur écoute sur http://127.0.0.1:8000 ; sa documentation est à /docs.
Seul backend/ est versionné. Les articles et le frontend restent externes à
cet historique. Pour la lecture, créer content/articles/ à côté de backend/,
ou définir WIKI_CONTENT_DIR vers un dossier contenant articles/.
Le verrou de dépendances conserve aussi les bibliothèques de l'atelier.

## Fonctionnalités disponibles

Application FastAPI, route d’accueil et environnement Python reproductible. Le dépôt ne contient que backend/.

## Tests

```bash
uv run python -B -m unittest discover -s tests -v
```

Les tests manipulent uniquement des fichiers temporaires. Chaque nouvelle
fonctionnalité possède sa vérification. Les tests précédents sont conservés
ou adaptés au refactor sans supprimer la vérification du comportement.

## Limites

Application locale, sans authentification. Le stockage doit être administré
de confiance. Les étapes de concurrence et de robustesse indiquées ci-dessus
ne sont présentes qu'une fois implémentées. Les fichiers séparés ne forment
pas une transaction résistante à une coupure brutale. Les opérations de
suppression par GET suivent le frontend et ne doivent pas être préchargées.
