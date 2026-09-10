from django.apps import AppConfig


class OpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ops"
    verbose_name = "Administration technique (ops)"

    def ready(self):
        import apps.ops.models