# SUNU MALL — Documentation Globale de l'Environnement

Bienvenue sur le dépôt de **SUNU MALL**, une place de marché (marketplace) sénégalaise en ligne permettant à chaque vendeur de gérer sa propre boutique (produits, commandes, livreurs), accessible via des interfaces web et mobiles.

Ce dépôt utilise une structure de **mono-repo** regroupant toutes les briques logicielles du projet.

---

## 👥 Rôles au sein de l'Équipe

| Rôle | Périmètre technique |
| :--- | :--- |
| **CTO (Lead Infra / DevOps & Backend)** | Architecture, déploiement, sécurité, base de données |
| **Développeur Backend** | API REST (Django DRF), tâches asynchrones (Celery) |

| **Développeuse Frontend** | Boutique publique (React/Vite) & Espaces vendeur / admin (React/Vite) |
| **Développeuse Mobile & IA** | Application Client (React Native) & Intégration IA |
| **Développeur Mobile, IA & DevOps** | App mobile, intégration IA et support infrastructure / CI-CD |

---

## 📁 Architecture du Mono-repo

```
sunu-mall/
├── backend/            # API REST - Django + Django REST Framework + Celery
├── frontend/           # Boutique publique + espaces vendeur/admin/livreur - React + Vite (SPA)
├── mobile/             # Application mobile Client - React Native (Expo)
├── infra/              # Configuration Docker Compose, Nginx, Variables d'env & Monitoring
│   ├── env/            # Variables d'environnement templates (dev, prod, staging)
│   ├── nginx/          # Configuration du reverse proxy de routage
│   ├── monitoring/     # Configuration Prometheus, Grafana & Loki
│   └── scripts/        # Scripts d'exploitation (migration, backup, restore, deploy)
└── docs/               # Documentations fonctionnelles et décisions d'architecture
```

---

## 🛠️ Configuration et Démarrage de l'Environnement Local

### 1. Prérequis
Assurez-vous d'avoir installé sur votre machine :
* [Docker](https://www.docker.com/) et **Docker Compose**
* [Git](https://git-scm.com/)
* [Node.js](https://nodejs.org/) (pour tester les frontends en local hors Docker si besoin)

### 2. Configuration des variables d'environnement
Avant de démarrer les conteneurs, vous devez dupliquer les fichiers d'environnement d'exemple et configurer vos clés secrètes :

```bash
# Configuration des services Docker (infra/env)
cp infra/env/backend.env.example infra/env/backend.env
cp infra/env/postgres.env.example infra/env/postgres.env
cp infra/env/redis.env.example infra/env/redis.env

# Configuration locale des projets (si vous les lancez hors Docker)
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 3. Lancement de la Stack de Développement
Pour lancer l'ensemble des services en local avec Docker Compose :

```bash
# Lancement en tâche de fond (détaché)
docker compose -f infra/docker-compose.dev.yml up --build -d

# Visualisation des logs du backend uniquement
docker compose -f infra/docker-compose.dev.yml logs -f backend
```

---

## 🌐 Adresses des Services et Consoles

Une fois la stack démarrée, les services suivants sont accessibles :

### 🚀 Points d'entrée Utilisateurs & API
* **Boutique en ligne (React/Vite) :** [http://localhost:3010](http://localhost:3010)
* **Espace vendeur :** [http://localhost:3010/merchant](http://localhost:3010/merchant)
* **API Backend Django (DRF) :** [http://localhost:8080/api/](http://localhost:8080/api/)
* **Administration Django :** [http://localhost:8080/admin/](http://localhost:8080/admin/)
* **Nginx Reverse Proxy (Global) :** [http://localhost:8081](http://localhost:8081)
  * `/` -> Redirige vers le Frontend
  * `/api/` -> Redirige vers le Backend (API)
  * `/admin/` -> Redirige vers l'Administration Django

### 📊 Stockage de Données & Outils d'Administration
* **Base de données PostgreSQL :** Accessible sur le port `5433` de la machine hôte
* **Interface PgAdmin :** [http://localhost:5051](http://localhost:5051) (Login par défaut : `admin@sunumall.com` / `admin`)
* **Console Web MinIO (S3) :** [http://localhost:9011](http://localhost:9011) (Identifiants : `minioadmin` / `minioadmin`)
* **API S3 MinIO (Stockage Media) :** [http://localhost:9010](http://localhost:9010)

---

## 📈 Monitoring et Supervision

La plateforme intègre une stack de surveillance prête pour la production pour mesurer la santé de nos conteneurs et analyser les pannes.

* **Prometheus :** [http://localhost:9091](http://localhost:9091) — Collecte en continu les métriques de la base de données, de Django et du système.
* **Grafana :** [http://localhost:3031](http://localhost:3031) — Permet de visualiser les métriques collectées via des tableaux de bord. (Identifiants : `admin` / mot de passe configuré dans Grafana).
* **Loki & Promtail (Centralisation des logs) :** Centralise les journaux de l'ensemble des conteneurs pour permettre une recherche rapide de pannes directement dans Grafana.

---

## 🗄️ Gestion de la Base de Données et Sauvegardes

Des scripts automatisés sont à votre disposition dans le dossier `infra/scripts/` :

* **Exécuter les migrations Django :**
  ```bash
  docker compose -f infra/docker-compose.dev.yml exec backend python manage.py migrate
  ```
* **Sauvegarder la base de données et les fichiers médias (MinIO) :**
  ```bash
  bash infra/scripts/backup.sh
  ```
  *(Crée une archive SQL et tar.gz dans un dossier `backups/`)*
* **Restaurer une sauvegarde :**
  ```bash
  bash infra/scripts/restore.sh <nom_du_fichier_sql> <nom_du_fichier_media>
  ```

---

## 🤝 Workflow Git et Règles de Contribution

Pour maintenir un code propre et éviter les conflits dans le mono-repo, toute l'équipe doit respecter le workflow suivant :

### 1. Stratégie de Branches (Gitflow)
* `main` : Contient le code stable en production. Aucun commit direct n'est autorisé.
* `develop` : Branche d'intégration. C'est à partir d'elle qu'on crée les branches de fonctionnalités et que l'on merge.
* `feature/<nom-fonctionnalite>` : Branche de travail créée depuis `develop`.

### 2. Règles de Commit (Conventional Commits)
Le format des messages de commit doit suivre le schéma suivant : `type(zone): description courte`

Exemples :
* `feat(backend): ajoute le modèle CustomUser avec 4 rôles`
* `fix(frontend): résout le problème de chargement du panier`
* `chore(infra): intègre Grafana Loki dans docker-compose`
* `docs(readme): met à jour le guide de démarrage de l'environnement`

### 3. Processus de Pull Request (PR)
1. Poussez votre branche feature sur GitHub et ouvrez une PR ciblant `develop`.
2. Complétez la description en expliquant le *quoi*, le *pourquoi* et la méthode de test.
3. Attendez le passage réussi des tests automatiques sur la CI (GitHub Actions).
4. Obtenez l'approbation d'un des relecteurs responsables désignés dans le fichier `CODEOWNERS`.
5. Fusionnez la PR en mode *Squash and Merge*.
