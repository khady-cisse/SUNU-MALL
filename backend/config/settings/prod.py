"""Settings pour la production. À utiliser via DJANGO_SETTINGS_MODULE=config.settings.prod"""
from django.core.exceptions import ImproperlyConfigured
from decouple import config, Csv
from .base import *  # noqa: F401,F403

DEBUG = False

# En production, pas de secret "par défaut" : si la variable manque, on
# refuse de démarrer (au lieu de partir avec une clé connue de tous).
DJANGO_SECRET_KEY = config("DJANGO_SECRET_KEY", default=None)
if not DJANGO_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY est obligatoire en production — "
        "renseignez-la dans infra/env/backend.env."
    )
SECRET_KEY = DJANGO_SECRET_KEY

# idem pour les hosts autorisés : vide en prod = 400 sur le domaine réel.
DJANGO_ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="", cast=Csv())
if not DJANGO_ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS est obligatoire en production — "
        "ex. DJANGO_ALLOWED_HOSTS=api.sunumall.sn,www.sunumall.sn"
    )
ALLOWED_HOSTS = DJANGO_ALLOWED_HOSTS

# TLS terminé par nginx : Django doit savoir que la requête arrive en https,
# sinon SECURE_SSL_REDIRECT boucle (il redirige les requêtes qu'il croit en http).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True