import logging

from .permissions import grant_default_access

logger = logging.getLogger(__name__)


def assign_to_ksiegowosc_group(strategy, details, user=None, *args, **kwargs):
    """Krok pipeline logowania Google: konto trafia do grupy „ksiegowosc”."""
    if user and user.pk:
        try:
            grant_default_access(user)
        except Exception:
            logger.exception("Nie udało się nadać dostępu kontu %s", user.username)

    return {}
