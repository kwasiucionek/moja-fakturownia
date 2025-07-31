from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from ksiegowosc.models import CompanyInfo, Contractor, Invoice, MonthlySettlement
import logging

logger = logging.getLogger(__name__)


def assign_to_ksiegowosc_group(strategy, details, user=None, *args, **kwargs):
    """
    Pipeline function to assign new users to 'ksiegowosc' group
    and grant necessary permissions
    """
    if user and user.pk:
        try:
            # Przypisz do grupy 'ksiegowosc'
            ksiegowosc_group, created = Group.objects.get_or_create(name='ksiegowosc')
            user.groups.add(ksiegowosc_group)

            # Ustaw jako staff (dostęp do panelu admina)
            if not user.is_staff:
                user.is_staff = True
                user.save()

            # Dodaj uprawnienia do modeli księgowości
            models_to_grant = [CompanyInfo, Contractor, Invoice, MonthlySettlement]
            permissions_to_grant = []

            for model in models_to_grant:
                content_type = ContentType.objects.get_for_model(model)
                permissions = Permission.objects.filter(content_type=content_type)
                permissions_to_grant.extend(permissions)

            user.user_permissions.set(permissions_to_grant)

            logger.info(f"User {user.username} assigned to ksiegowosc group with permissions")

        except Exception as e:
            logger.error(f"Error assigning user {user.username} to ksiegowosc group: {e}")

    return {}
