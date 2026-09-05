"""Settings pour le développement local. Importé par défaut via manage.py."""
from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Désactiver le throttle de connexion en dev et dans les tests : il s'applique
# en prod (config/settings/base.py). On ne repose pas sur DEBUG car Django
# force DEBUG=False pendant `manage.py test`.
AUTH_ANON_THROTTLE_RATE = None

# Retirer debug toolbar pour éviter les erreurs temporaires
# INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405

# INTERNAL_IPS = ["127.0.0.1"]

# DATABASES est hérité de base.py (Postgres, via infra/docker-compose.dev.yml + pgAdmin)
