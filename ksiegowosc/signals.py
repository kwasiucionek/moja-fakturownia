# ksiegowosc/signals.py

import logging

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .permissions import grant_default_access

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def assign_new_user_to_ksiegowosc(sender, instance, created, raw=False, **kwargs):
    """Nowe zwykłe konto (rejestracja, Google, panel) trafia do grupy „ksiegowosc”."""
    if not created or raw:
        return
    try:
        grant_default_access(instance)
    except Exception:
        logger.exception("Nie udało się nadać dostępu kontu %s", instance.username)
