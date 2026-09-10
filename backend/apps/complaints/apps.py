from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.complaints"
    verbose_name = "Plaintes et tickets support"

    def ready(self):
        import apps.complaints.models