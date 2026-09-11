# =========================================================
# SUNU MALL — Backend (Django + DRF + Celery + app IA)
# Build multi-stage : pas de compilateurs ni de caches pip
# dans l'image finale, juste le code + les libs nécessaires.
# =========================================================

# ---- Stage 1 : build des dépendances ----
FROM python:3.12-slim AS builder

WORKDIR /app

# Dépendances système nécessaires UNIQUEMENT à la compilation
# (psycopg2, Pillow, etc. en ont besoin pour builder leurs wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

# On choisit le fichier de requirements selon l'environnement.
# base.txt = Django/DRF/Celery/Redis/Postgres (toujours nécessaire)
# ia.txt   = libs IA (souvent lourdes : numpy, torch, transformers...)
# dev.txt  = outils de dev (pytest, flake8...), jamais en prod
ARG REQUIREMENTS_FILE=requirements/base.txt
RUN pip install --no-cache-dir --user -r ${REQUIREMENTS_FILE}

# ---- Stage 2 : image finale, légère ----
FROM python:3.12-slim

WORKDIR /app

# Seulement les libs système nécessaires À L'EXÉCUTION (pas à la compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# On récupère uniquement les packages Python déjà compilés, pas les outils de build
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . .

# Statique (admin Django + thème) collectée dès l'image : nginx/WhiteNoise
# la servent sans étape runtime. configure settings/dev = DEBUG=True mais
# collectstatic ne touche ni à la base ni aux secrets.
RUN python manage.py collectstatic --noinput

EXPOSE 8001

# En dev, ce CMD est écrasé par docker-compose (reload activé).
# En prod, on utilisera gunicorn (voir infra/).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
