# Comment contribuer

## Branches

On suit Gitflow, simplifié :

- `main` — toujours stable, c'est ce qui est en production.
- `develop` — intégration : tout ce qui est prêt mais pas encore livré.
- `feature/<nom-court>` — une branche par fonctionnalité/ticket, créée **depuis `develop`**, jamais depuis `main`.

```bash
git checkout develop
git pull origin develop
git checkout -b feature/panier-livraison
```

## Commits

Format recommandé (Conventional Commits) :

```
type(zone): description courte au présent

feat(backend): ajoute l'endpoint de recommandations IA
fix(mobile): corrige le crash à l'ouverture du panier
chore(infra): met à jour l'image Postgres
```

Types courants : `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
Zones courantes : `backend`, `frontend`, `mobile`, `ia`, `infra`.

## Pull Requests

1. Pousse ta branche, ouvre une PR vers `develop` (pas vers `main` directement).
2. Remplis le template de PR (quoi, pourquoi, comment tester).
3. La CI doit passer (build + lint + tests) avant de demander une review.
4. Le CODEOWNERS de la zone touchée doit approuver (voir `.github/CODEOWNERS`).
5. Une fois approuvé : merge dans `develop`.

`main` ne reçoit que des merges depuis `develop`, au moment d'une release.

## Versioning

On suit SemVer (`MAJOR.MINOR.PATCH`), ex : `1.2.3`.

- **MAJOR** : changement de fond, potentiellement incompatible (ex: refonte du système de paiement)
- **MINOR** : nouvelle fonctionnalité (ex: ajout du paiement Wave)
- **PATCH** : correction de bug (ex: prix mal affiché)

```bash
git tag -a v1.0.0 -m "Version 1.0.0"
git push origin v1.0.0
```

## Dockerfile

Chaque service garde son `Dockerfile` à jour. Règle simple : si tu ajoutes une dépendance à un service, vérifie que le `Dockerfile`/`requirements`/`package.json` correspondant la liste bien — l'objectif est qu'aucun service n'installe une dépendance dont il n'a pas besoin (ex: le mobile ne doit jamais tirer les libs IA du backend).

## Conflits

En cas de conflit Git : ne jamais merger à l'aveugle. Lire les marqueurs `<<<<<<<` / `=======` / `>>>>>>>`, choisir/fusionner la bonne version, supprimer les marqueurs, puis `git add` + `git commit`.

Pour limiter les conflits : `git pull origin develop` régulièrement sur ta branche feature.
