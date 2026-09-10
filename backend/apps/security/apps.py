from django.apps import AppConfig


class SecurityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.security"
    verbose_name = "Sécurité (journal des actions sensibles)"

    def ready(self):
        import apps.security.models