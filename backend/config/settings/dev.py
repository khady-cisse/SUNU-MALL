"""Settings pour le développement local. Importé par défaut via manage.py."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Origines locales autorisées pour la vérification CSRF (admin Django et
# POST /api/ depuis le SPA). Sans cela, Django refuse les POST dont l'en-tête
# Origin ne correspond pas à un Host "de confiance" (ex: 403 sur l'admin
# depuis http://localhost:8081).
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:3010",
    "http://localhost:3004",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
]

# Désactiver le throttle de connexion en dev et dans les tests : il s'applique
# en prod (config/settings/base.py). On ne repose pas sur DEBUG car Django
# force DEBUG=False pendant `manage.py test`.
AUTH_ANON_THROTTLE_RATE = None

# Aucun fournisseur SMS n'étant branché, on révèle le code OTP téléphone
# dans la réponse de l'endpoint d'envoi pour le développement. Les settings
# de test l'activent via override_settings ciblé (base.py le garde à False).
PHONE_OTP_REVEAL_CODE = True

# Hachage de mot de passe rapide pour le développement et la suite de tests :
# PBKDF2 à 6 000 000 itérations (défaut Django) prend >1 s par hash sur ce
# poste et fait exploser la durée des tests. Jamais utilisé en production
# (prod.py n'hérite pas de ce réglage) — le format reste du PBKDF2 compatible.
from django.contrib.auth.hashers import PBKDF2PasswordHasher  # noqa: E402


class _FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    iterations = 10_000


PASSWORD_HASHERS = ["config.settings.dev._FastPBKDF2PasswordHasher"]

# Retirer debug toolbar pour éviter les erreurs temporaires
# INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405

# INTERNAL_IPS = ["127.0.0.1"]

# DATABASES est hérité de base.py (Postgres, via infra/docker-compose.dev.yml + pgAdmin)
