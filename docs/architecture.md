# Décisions d'architecture

Ce document explique le **pourquoi** des choix structurants du repo, pour que toute l'équipe comprenne la logique (et puisse la remettre en question si le contexte change).

## Mono-repo plutôt que multi-repo

À 4 personnes avec un backend et une IA fortement couplés (Celery, Redis, Postgres partagés), le coût de coordination entre plusieurs repos (PR synchronisées, contrats d'API à dupliquer) dépasse les bénéfices du multi-repo (permissions isolées, CI ultra-simple). Le mono-repo permet une seule PR pour une feature qui touche backend + frontend, un seul historique, un seul `docker-compose` pour tout lancer en local.

**Quand reconsidérer ce choix** : si l'équipe grossit fortement (10+ devs), ou qu'un service (ex: l'IA) devient un produit à part avec sa propre équipe et son propre rythme de release. Migrer un dossier mono-repo vers un repo séparé est une opération standard (`git filter-repo`) — l'inverse est plus coûteux, donc partir en mono-repo n'est pas un choix qui enferme.

## App IA intégrée au backend Django (pour l'instant)

L'IA vit dans `backend/apps/ia/`, comme une app Django normale, plutôt que dans un service séparé. Pour que cette décision reste réversible facilement :

- Les dépendances IA sont isolées dans `backend/requirements/ia.txt`, séparées de `base.txt`. Si l'app IA finit par avoir besoin de torch/transformers/etc., le reste du backend n'a pas à porter ce poids.
- Tout traitement IA potentiellement lent passe par une tâche Celery (`apps/ia/tasks.py`), jamais directement dans une vue HTTP — ça évite de bloquer une requête web pendant une inférence.

**Signal qu'il est temps d'extraire l'IA en service à part** : si l'image Docker du backend devient lourde (plusieurs Go) à cause des libs IA, ou si l'IA a besoin d'un cycle de déploiement complètement différent du reste du backend (ex: GPU dédié).

## Une seule SPA React + Vite pour boutique et espaces métiers

`frontend/` regroupe **toute** l'interface web : boutique publique **et** espaces vendeur, livreur, admin. C'est un choix assumé aujourd'hui :

- Une seule application, une seule UI-kit, un seul parcours de build — maintenance simple pour une petite équipe (4 devs).
- L'espace vendeur est **privé** (jamais indexé par un moteur de recherche) : inutile d'y faire du rendu serveur.
- La boutique est servie en **SPA** (Vite + react-router) : aucun SSR pour l'instant.

**Ce qu'on accepte comme risque** : le référencement de la boutique est plus faible que celui d'un rendu côté serveur. Si l'acquisition Google devient une cible prioritaire, on pourra intégrer le rendu côté serveur (`vite-plugin-ssr` par exemple) **sans changer d'app** — la séparation en composants le permet.

## Pourquoi un Dockerfile multi-stage par service

Chaque `Dockerfile` du repo suit le même principe : une étape de build (avec compilateurs, outils, dépendances complètes) puis une étape finale qui ne copie que le strict nécessaire à l'exécution. Concrètement :

- Le backend n'embarque pas `build-essential` dans son image finale (utile seulement pour compiler `psycopg2`, par exemple).
- Le frontend React/Vite n'embarque pas son code source ni les dépendances de développement, seulement le build statique généré (images, JS, CSS) servi par nginx.
- Le dashboard vendeur n'embarque même pas Node.js dans l'image finale — juste nginx + les fichiers statiques générés.

Ça réduit la taille des images, accélère les déploiements, et réduit la surface d'attaque (moins d'outils inutiles présents en prod).

## Pourquoi les CI sont scindées par dossier (`paths:`)

Chaque workflow GitHub Actions (`backend.yml`, `frontend.yml`, etc.) ne se déclenche que si son dossier a changé. Ça évite de relancer tout le pipeline Django quand seul le frontend a bougé — gain de temps et de lisibilité (chacun voit directement quelle CI le concerne sur sa PR).
