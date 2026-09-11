"""
Settings Django partagés par tous les environnements.
dev.py et prod.py importent ce fichier puis surchargent ce qui change.
"""
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="change-moi-en-production")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "storages",
    "drf_spectacular",
    # Apps métier SUNU MALL — chacune correspond à un domaine clair
    "apps.users",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.monetization",
    "apps.shopping",
    "apps.analytics",
    "apps.ia",
    "apps.auth",
    "apps.kyc",
    "apps.commissions",
    "apps.security",
    "apps.ops",
    "apps.complaints",
    "apps.search",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.security.middleware.RequestIDMiddleware",
    "apps.security.middleware.MaintenanceModeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données (Postgres, voir infra/docker-compose.yml) ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="sunu_mall"),
        "USER": config("POSTGRES_USER", default="sunu_mall"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="sunu_mall"),
        "HOST": config("POSTGRES_HOST", default="db"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

# --- Redis (cache + broker Celery) ---
REDIS_URL = config("REDIS_URL", default="redis://redis:6379/0")

# --- Celery ---
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# Tâches planifiées (Celery Beat). L'expiration des abonnements et les
# rappels "expire bientôt" tournaient dans SubscriptionViewSet.get_queryset
# (des écritures/emails à la simple lecture) ; elles sont ici, quotidiennes.
CELERY_BEAT_SCHEDULE = {
    "expire-and-remind-subscriptions-daily": {
        "task": "apps.monetization.tasks.expire_and_remind_subscriptions",
        "schedule": 24 * 60 * 60,  # toutes les 24h
    },
    "release-pending-funds-daily": {
        "task": "apps.commissions.tasks.release_pending_funds_task",
        "schedule": 24 * 60 * 60,  # toutes les 24h
    },
}

# --- Stockage fichiers (MinIO, compatible API S3) ---
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
AWS_ACCESS_KEY_ID = config("MINIO_ACCESS_KEY", default="minioadmin")
AWS_SECRET_ACCESS_KEY = config("MINIO_SECRET_KEY", default="minioadmin")
AWS_STORAGE_BUCKET_NAME = config("MINIO_BUCKET", default="sunu-mall")
AWS_S3_ENDPOINT_URL = config("MINIO_ENDPOINT", default="http://minio:9000")
AWS_S3_USE_SSL = config("MINIO_USE_SSL", default=False, cast=bool)
# Le endpoint ci-dessus (nom de service Docker) n'est joignable que depuis
# l'intérieur du réseau Docker. Pour que les URLs d'images générées soient
# accessibles depuis le navigateur, on force le domaine public si fourni,
# et on désactive la signature de requête (le bucket est en lecture publique).
AWS_QUERYSTRING_AUTH = False
AWS_DEFAULT_ACL = None
_minio_public_endpoint = config("MINIO_PUBLIC_ENDPOINT", default="")
# Exposé comme réglage public pour que le cache des URLs signées KYC puisse
# signer directement contre cet hôte (voir apps/kyc/storage.signed_url).
MINIO_PUBLIC_ENDPOINT = _minio_public_endpoint
if _minio_public_endpoint:
    # MinIO utilise l'adressage "path-style" (endpoint/bucket/clé), pas le
    # style "virtual-hosted" (bucket.endpoint/clé) que django-storages suppose
    # par défaut pour AWS_S3_CUSTOM_DOMAIN — on inclut donc le bucket dedans.
    AWS_S3_CUSTOM_DOMAIN = f"{_minio_public_endpoint}/{AWS_STORAGE_BUCKET_NAME}"
    AWS_S3_URL_PROTOCOL = "https:" if AWS_S3_USE_SSL else "http:"

# --- Stockage KYC (pièces d'identité, bucket PRIVÉ dédié) ---
# Les documents KYC sont hébergés dans un bucket privé séparé du bucket public
# (`sunu-mall-private`). Ils restent inaccessibles en lecture publique et ne
# sont exposés qu'à travers des URLs pré-signées à courte durée (TLS de 300s),
# générées par Django après contrôle des permissions. Le backend "fs" (système
# de fichiers local) est réservé aux tests : la suite s'exécute ainsi sans
# MinIO. Voir apps/kyc/storage.py.
KYC_STORAGE_BACKEND = config("KYC_STORAGE_BACKEND", default="s3")
KYC_STORAGE_BUCKET = config("KYC_STORAGE_BUCKET", default="sunu-mall-private")
KYC_STORAGE_LOCATION = config("KYC_STORAGE_LOCATION", default=str(BASE_DIR / "media_kyc"))
KYC_PRESIGNED_URL_TTL = config("KYC_PRESIGNED_URL_TTL", default=300, cast=int)

# --- Commission et portefeuilles vendeurs (apps/commissions) ---
# Durée de l'essai à 0 % de commission à partir de la création du compte (§3).
COMMISSION_TRIAL_DAYS = config("COMMISSION_TRIAL_DAYS", default=30, cast=int)
# Période de grâce après expiration de l'essai ou de l'abonnement pendant
# laquelle le vendeur continue de vendre au taux de son dernier plan (§18) —
# au-delà, il ne reçoit plus de nouvelles commandes.
COMMISSION_GRACE_DAYS = config("COMMISSION_GRACE_DAYS", default=7, cast=int)
# Délai de libération des fonds d'une vente livrée (pending → available, §9).
COMMISSION_RELEASE_DAYS = config("COMMISSION_RELEASE_DAYS", default=3, cast=int)

# --- Abonnement vendeur (apps/monetization) ---
# Période de grâce après expiration d'un abonnement STARTER/PRO/BUSINESS
# pendant laquelle le vendeur reçoit encore des commandes et peut modifier
# ses produits (spec monétisation §11). Ne jamais coder en dur.
SUBSCRIPTION_GRACE_PERIOD_DAYS = config("SUBSCRIPTION_GRACE_PERIOD_DAYS", default=7, cast=int)
# Rappels « votre abonnement expire bientôt » envoyés avant la fin de période,
# configurables (jours avant expiration). Tâche Celery quotidienne.
SUBSCRIPTION_REMINDER_DAYS = [int(d) for d in config(
    "SUBSCRIPTION_REMINDER_DAYS", default="7,3,1", cast=str
).split(",") if d.strip().isdigit()]
# Secrets des fournisseurs de paiement pour la validation des webhooks.
# Si vide, les webhooks ne sont acceptés qu'en mode sandbox (PAYMENT_SANDBOX).
PAYMENT_PROVIDERS = {
    "wave": config("WAVE_WEBHOOK_SECRET", default=""),
    "orange_money": config("ORANGE_MONEY_WEBHOOK_SECRET", default=""),
}

# --- Confirmation de livraison par code OTP ---
# Le client valide la réception d'une commande avec un code à 6 chiffres
# que le livreur lui remet physiquement. Validité courte et essais limités.
CONFIRMATION_OTP_TTL_MINUTES = config("CONFIRMATION_OTP_TTL_MINUTES", default=30, cast=int)
MAX_OTP_ATTEMPTS = config("MAX_OTP_ATTEMPTS", default=5, cast=int)

# --- Journal de sécurité (apps/security) ---
# Durée de rétention des journaux d'actions sensibles avant leur purge
# automatique (politique de conservation des données, spec §17).
SECURITY_LOG_RETENTION_DAYS = config("SECURITY_LOG_RETENTION_DAYS", default=365, cast=int)
# Mise hors service du journal (tests, démo) sans restaurer l'ancien code.
DISABLE_SECURITY_LOGS = config("DISABLE_SECURITY_LOGS", default=False, cast=bool)

# --- Vérification du téléphone par code OTP ---
# Code à 6 chiffres à durée de vie courte et essais limités. L'envoi SMS est
# branché sur le canal Notification.SMS (apps/monetization) : sans fournisseur
# configuré, le code est tracé et loggé en console — voir
# apps/auth/views.RequestPhoneOTPView pour le branchement du fournisseur.
PHONE_OTP_TTL_MINUTES = config("PHONE_OTP_TTL_MINUTES", default=10, cast=int)
PHONE_OTP_MAX_ATTEMPTS = config("PHONE_OTP_MAX_ATTEMPTS", default=5, cast=int)
# REVEAL : retourner le code OTP dans la réponse de la requête d'envoi.
# STRICTEMENT réservé au développement/test (env PHONE_OTP_REVEAL_CODE=true
# dans config/settings/dev.py) — JAMAIS en production : le code doit arriver
# uniquement par SMS sur le téléphone de l'utilisateur.
PHONE_OTP_REVEAL_CODE = config("PHONE_OTP_REVEAL_CODE", default=False, cast=bool)

# --- Affectation des courses ---
# Un livreur ne reçoit une commande que s'il est à moins de ce rayon (km) de
# la boutique : il doit être assez proche pour venir récupérer le colis.
DRIVER_ASSIGNMENT_RADIUS_KM = config("DRIVER_ASSIGNMENT_RADIUS_KM", default=5, cast=float)

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Chaque appel coûte réellement de l'argent (API Anthropic) : limite
        # volontairement basse pour éviter qu'un usage abusif ne fasse
        # exploser la facture. Ne s'applique qu'aux vues qui déclarent
        # throttle_scope = "ai" (apps/ia/views.py) — aucune autre vue du
        # projet n'a de scope "ai", donc ce throttle ne les affecte pas.
        "ai": "20/hour",
    },
}

# Throttle anti-brute-force des endpoints d'authentification (register, login,
# resend de vérification, guest-checkout, obtention de JWT). Rate fixé ici pour
# la production ; config/settings/dev.py le désactive (None) pour le dev et les
# tests. On ne s'appuie PAS sur settings.DEBUG car Django force DEBUG=False
# pendant `manage.py test`.
AUTH_ANON_THROTTLE_RATE = "10/min"

# DRF Spectacular (Swagger/OpenAPI)
SPECTACULAR_SETTINGS = {
    "TITLE": "SUNU MALL API",
    "DESCRIPTION": "Marketplace sénégalais — API REST",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# JWT Settings
from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": config("DJANGO_SECRET_KEY", default="change-moi-en-production"),
    "VERIFYING_KEY": "",
    "AUDIENCE": None,
    "ISSUER": None,
    "JSON_ENCODER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=60),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}

# --- CORS : autorise le frontend Vite (dev), nginx ---
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://localhost:3004,http://localhost:3010,http://localhost:3011,http://localhost:8081",
    cast=Csv(),
)

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Dakar"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Statique maison (thème de l'admin Django, etc.) servie en plus de la
# statique de Django et des applications en développement.
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email Configuration
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=1025, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@sunumall.com")

# --- Paiement (Wave / Orange Money) ---
# PAYMENT_SANDBOX doit être explicitement mis à False en production ET en
# recette avec de vraies clés marchandes. Le défaut est False : un déploiement
# oublieux ne doit jamais tourner silencieusement en paiements simulés.
PAYMENT_SANDBOX = config("PAYMENT_SANDBOX", default=False, cast=bool)

# Wave — API Business (Checkout) : clé marchande du dev portal
# (business.wave.com/dev-portal). WAVE_API_BASE_URL permet de pointer une
# éventuelle passerelle de test ; par défaut l'API publique Wave.
WAVE_API_KEY = config("WAVE_API_KEY", default="")
WAVE_API_BASE_URL = config("WAVE_API_BASE_URL", default="https://api.wave.com")

# Orange Money — API Web Payment : le jeton d'accès est obtenu par OAuth2
# (client_id/client_secret), puis chaque paiement est signé par la
# merchant_key reçue à l'onboarding. ORANGE_MONEY_COUNTRY_PATH est le segment
# pays de l'endpoint de production ("sn" au Sénégal) ; le sandbox, lui,
# passe toujours par "/dev/". ORANGE_MONEY_CURRENCY reste sur XOF (OUV dans
# certains environnements de test).
ORANGE_MONEY_CLIENT_ID = config("ORANGE_MONEY_CLIENT_ID", default=config("ORANGE_MONEY_API_KEY", default=""))
ORANGE_MONEY_CLIENT_SECRET = config("ORANGE_MONEY_CLIENT_SECRET", default="")
ORANGE_MONEY_MERCHANT_KEY = config("ORANGE_MONEY_MERCHANT_KEY", default="")
ORANGE_MONEY_API_BASE_URL = config("ORANGE_MONEY_API_BASE_URL", default="https://api.orange.com")
ORANGE_MONEY_COUNTRY_PATH = config("ORANGE_MONEY_COUNTRY_PATH", default="sn")
ORANGE_MONEY_CURRENCY = config("ORANGE_MONEY_CURRENCY", default="XOF")

# URL du frontend utilisée pour construire les liens dans les emails et les
# URL de retour des passerelles (success_url/error_url). BACKEND_URL est
# l'URL publique de l'API : c'est elle que Wave/Orange Money notifient
# (notif_url), pas le frontend. Doivent être accessibles publiquement.
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3004")
BACKEND_URL = config("BACKEND_URL", default="http://localhost:8080/api")

# --- IA (apps/ia/) : génération de description produit, assistant client ---
# Tant qu'aucune clé n'est fournie, les endpoints IA répondent une erreur
# claire (503) plutôt que de planter — voir apps/ia/services.py.
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
