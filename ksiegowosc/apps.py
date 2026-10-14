from django.apps import AppConfig
from django.db.models.signals import post_migrate


class KsiegowoscConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ksiegowosc"

    def ready(self):
        from . import signals  # noqa: F401 — rejestracja sygnałów
        from .permissions import sync_group_permissions

        # Po każdej migracji uprawnienia grupy „ksiegowosc” są zgodne z GROUP_PERMISSIONS
        post_migrate.connect(
            sync_group_permissions, dispatch_uid="ksiegowosc_group_perms"
        )
