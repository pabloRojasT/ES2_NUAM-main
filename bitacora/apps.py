from django.apps import AppConfig
from django.db.models.signals import post_migrate


class BitacoraConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bitacora"
    verbose_name = "Bitácora"

    def ready(self):
        from .bloqueos import instalar_bloqueos

        post_migrate.connect(instalar_bloqueos, sender=self)
