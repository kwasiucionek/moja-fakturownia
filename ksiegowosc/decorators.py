# ksiegowosc/decorators.py

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import CompanyInfo


def company_info_required(view_func):
    """
    Dekorator sprawdzający czy użytkownik ma uzupełnione dane firmy
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        try:
            company_info = CompanyInfo.objects.get(user=request.user)
            # Sprawdź podstawowe pola
            if not all([company_info.company_name, company_info.tax_id, 
                       company_info.street, company_info.city]):
                messages.warning(
                    request,
                    'Uzupełnij wszystkie wymagane dane firmy, aby kontynuować.'
                )
                return redirect('admin:ksiegowosc_companyinfo_change', company_info.pk)
        except CompanyInfo.DoesNotExist:
            messages.warning(
                request,
                'Musisz najpierw dodać dane swojej firmy.'
            )
            return redirect('admin:ksiegowosc_companyinfo_add')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def ksiegowosc_group_required(view_func):
    """
    Dekorator sprawdzający czy użytkownik należy do grupy ksiegowosc
    """
    def check_group(user):
        return user.is_superuser or user.groups.filter(name='ksiegowosc').exists()
    
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not check_group(request.user):
            messages.error(
                request,
                'Nie masz uprawnień do tej funkcji.'
            )
            return redirect('auth:login')
        return view_func(request, *args, **kwargs)
    
    return user_passes_test(check_group)(view_func)

