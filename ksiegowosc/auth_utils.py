# ksiegowosc/auth_utils.py

from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from .models import CompanyInfo
import logging

logger = logging.getLogger(__name__)


def create_ksiegowosc_group():
    """Utwórz grupę ksiegowosc z odpowiednimi uprawnieniami"""
    try:
        group, created = Group.objects.get_or_create(name='ksiegowosc')
        
        if created:
            # Dodaj uprawnienia do modeli księgowości
            from .models import (CompanyInfo, Contractor, Invoice, MonthlySettlement, 
                               YearlySettlement, ZUSRates, Payment, PurchaseInvoice, ExpenseCategory)
            
            models_to_grant = [
                CompanyInfo, Contractor, Invoice, MonthlySettlement,
                YearlySettlement, ZUSRates, Payment, PurchaseInvoice, ExpenseCategory
            ]
            
            for model in models_to_grant:
                content_type = ContentType.objects.get_for_model(model)
                permissions = Permission.objects.filter(content_type=content_type)
                group.permissions.set(permissions)
            
            logger.info("Created ksiegowosc group with permissions")
        
        return group
        
    except Exception as e:
        logger.error(f"Error creating ksiegowosc group: {e}")
        return None


def assign_user_to_ksiegowosc(user):
    """Przypisz użytkownika do grupy ksiegowosc"""
    try:
        group = create_ksiegowosc_group()
        if group:
            user.groups.add(group)
            if not user.is_staff:
                user.is_staff = True
                user.save()
            logger.info(f"Assigned user {user.username} to ksiegowosc group")
            return True
    except Exception as e:
        logger.error(f"Error assigning user {user.username} to ksiegowosc group: {e}")
    return False


def check_user_company_info(user):
    """Sprawdź czy użytkownik ma kompletne dane firmy"""
    try:
        company_info = CompanyInfo.objects.get(user=user)
        required_fields = ['company_name', 'tax_id', 'street', 'city', 'zip_code']
        
        missing_fields = []
        for field in required_fields:
            if not getattr(company_info, field, '').strip():
                missing_fields.append(field)
        
        return len(missing_fields) == 0, missing_fields
        
    except CompanyInfo.DoesNotExist:
        return False, ['company_info_not_exists']


def get_user_stats():
    """Pobierz statystyki użytkowników"""
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    staff_users = User.objects.filter(is_staff=True).count()
    ksiegowosc_users = User.objects.filter(groups__name='ksiegowosc').count()
    users_with_company = User.objects.filter(companyinfo__isnull=False).count()
    
    return {
        'total': total_users,
        'active': active_users,
        'staff': staff_users,
        'ksiegowosc': ksiegowosc_users,
        'with_company': users_with_company,
    }
