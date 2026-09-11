#!/bin/bash
# =========================================================
# SUNU MALL — Script de déploiement (production)
#
# Prérequis, à faire UNE fois sur le serveur :
#   1. git clone du repo + passage sur la branche main/develop
#   2. copier infra/env/*.example vers infra/env/*.env et y mettre les vrais
#      secrets (DJANGO_SECRET_KEY, POSTGRES_PASSWORD, MINIO, WEBHOOKS...)
#   3. placer les certificats TLS dans infra/nginx/ssl/
#      (fullchain.pem + privkey.pem) — sans eux nginx ne démarre pas
#   4. exporter PUBLIC_DOMAIN (ex: export PUBLIC_DOMAIN=sunumall.sn)
#
# Utilisation : bash infra/scripts/deploy.sh
# =========================================================

set -euo pipefail

# Chemin absolu du compose, quel que soit le répertoire d'appel du script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/../docker-compose.prod.yml"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "❌ Docker Compose introuvable sur ce serveur."
    exit 1
fi

if [ -z "${PUBLIC_DOMAIN:-}" ]; then
    echo "❌ Variable PUBLIC_DOMAIN manquante."
    echo "   Copier infra/env/compose.env.example vers infra/env/compose.env,"
    echo "   renseigner les valeurs puis relancer ce script (ou exporter PUBLIC_DOMAIN)."
    exit 1
fi

echo "🚀 Déploiement SUNU MALL (domaine : $PUBLIC_DOMAIN)..."

# Charge infra/env/compose.env s'il existe (PUBLIC_DOMAIN + identifiants
# compose). Les variables déjà présentes dans l'environnement ne sont pas
# écrasées ; sans ce fichier, il faut les exporter manuellement.
COMPOSE_ENV="$SCRIPT_DIR/../env/compose.env"
if [ -f "$COMPOSE_ENV" ]; then
    echo "📄 Chargement de infra/env/compose.env..."
    set -a
    # shellcheck disable=SC1090
    source "$COMPOSE_ENV"
    set +a
else
    echo "⚠️  infra/env/compose.env absent — variables compose à exporter manuellement."
fi

# Pull les dernières modifications du dépôt (branche courante).
echo "📥 Mise à jour du code..."
git pull --ff-only

# Télécharger les images épinglees (postgres, redis, minio, prometheus, ...)
echo "📦 Récupération des images de base..."
docker compose -f "$COMPOSE_FILE" pull --ignore-pull-failures

# Build (backend, frontend, nginx) puis recréation SANS arrêt total :
# compose ne recrée que les services dont la config/image a changé.
echo "🔨 Build + démarrage des services..."
docker compose -f "$COMPOSE_FILE" up -d --build

# Migrations de schéma avant de servir le nouveau trafic.
echo "📊 Application des migrations..."
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py migrate --noinput

# Statique déjà embarquée dans l'image ; on la re-collecte au cas où le
# déploiement réutilise une ancienne image (idempotent, sans coupure).
echo "🗂️ Recollecte de la statique..."
docker compose -f "$COMPOSE_FILE" exec -T backend python manage.py collectstatic --noinput

echo "✅ Déploiement terminé."

echo
echo "Prochaines étapes si premières fois :"
echo "  docker compose -f $COMPOSE_FILE exec backend python manage.py create_admin"
echo "  docker compose -f $COMPOSE_FILE exec backend python manage.py seed_demo"
echo "  docker compose -f $COMPOSE_FILE ps"