# ksiegowosc/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from .models import CompanyInfo, Contractor, Invoice, MonthlySettlement
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def assign_new_user_to_ksiegowosc(sender, instance, created, **kwargs):
    """
    Automatycznie przypisuj nowych użytkowników do grupy ksiegowosc
    """
    if created and not instance.is_superuser:
        try:
            # Przypisz do grupy
            ksiegowosc_group, group_created = Group.objects.get_or_create(name='ksiegowosc')
            instance.groups.add(ksiegowosc_group)
            
            # Ustaw is_staff
            instance.is_staff = True
            instance.save()
            
            # Dodaj uprawnienia
            models_to_grant = [CompanyInfo, Contractor, Invoice, MonthlySettlement]
            permissions_to_grant = []
            
            for model in models_to_grant:
                content_type = ContentType.objects.get_for_model(model)
                permissions = Permission.objects.filter(content_type=content_type)
                permissions_to_grant.extend(permissions)
            
            instance.user_permissions.set(permissions_to_grant)
            
            logger.info(f"New user {instance.username} assigned to ksiegowosc group")
            
        except Exception as e:
            logger.error(f"Error assigning new user {instance.username} to ksiegowosc group: {e}")
