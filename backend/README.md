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

GET /article/{article_identifier} lit un fichier UTF-8 et expose son nom, son identifiant et sa source. Un article absent donne 404.

Le champ content devient du HTML ; source conserve le Markdown. Le mode d’échappement empêche le HTML brut d’être exécuté.

Les identifiants vides ou contenant des fragments interdits sont refusés. Les liens symboliques sont rejetés et les erreurs de stockage distinguées de l’absence d’un article.

Le contrat Article est défini dans models.py, sans changer le JSON retourné.

config.py centralise le répertoire des articles et permet de le remplacer avec WIKI_CONTENT_DIR.

article.py porte la lecture et les validations. exceptions.py et storage.py restent indépendants de HTTP ; main.py traduit leurs exceptions.

rendering.py transforme les données d’un article en réponse HTML/Markdown. Il ne lit ni n’écrit de fichier.

GET /list renvoie les articles triés et exclut JSON, images, dossiers, liens et identifiants invalides.

POST /create valide le nom et le Markdown, génère l’identifiant et renvoie 201. Une création ne remplace pas un fichier existant ; un doublon donne 409.

Un RLock protège les opérations simultanées des threads du même processus, dont les créations concurrentes.

fcntl.flock étend la coordination aux processus du backend qui partagent le même stockage. Cette implémentation cible macOS/Linux.

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
