# ksiegowosc/auth_backends.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from .models import CompanyInfo, Contractor, Invoice, MonthlySettlement
import logging

logger = logging.getLogger(__name__)


class KsiegowoscBackend(ModelBackend):
    """
    Custom authentication backend that automatically assigns permissions
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username, password, **kwargs)
        
        if user:
            self.ensure_user_permissions(user)
        
        return user

    def ensure_user_permissions(self, user):
        """Upewnij się, że użytkownik ma odpowiednie uprawnienia"""
        try:
            # Przypisz do grupy ksiegowosc jeśli nie jest superuserem
            if not user.is_superuser:
                ksiegowosc_group, created = Group.objects.get_or_create(name='ksiegowosc')
                user.groups.add(ksiegowosc_group)
                
                # Ustaw is_staff
                if not user.is_staff:
                    user.is_staff = True
                    user.save()
                
                # Dodaj uprawnienia do modeli księgowości
                self.assign_ksiegowosc_permissions(user)
                
        except Exception as e:
            logger.error(f"Error ensuring permissions for user {user.username}: {e}")

    def assign_ksiegowosc_permissions(self, user):
        """Przypisz uprawnienia do modeli księgowości"""
        models_to_grant = [CompanyInfo, Contractor, Invoice, MonthlySettlement]
        permissions_to_grant = []
        
        for model in models_to_grant:
            content_type = ContentType.objects.get_for_model(model)
            permissions = Permission.objects.filter(content_type=content_type)
            permissions_to_grant.extend(permissions)
        
        user.user_permissions.set(permissions_to_grant)
