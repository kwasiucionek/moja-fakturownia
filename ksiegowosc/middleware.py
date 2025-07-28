# ksiegowosc/middleware.py

from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import CompanyInfo
import logging

logger = logging.getLogger(__name__)


class CompanyInfoRequiredMiddleware:
    """
    Middleware sprawdzający czy zalogowany użytkownik ma uzupełnione dane firmy.
    Jeśli nie, przekierowuje do formularza dodawania danych firmy.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Ścieżki, które nie wymagają danych firmy
        self.exempt_paths = [
            '/auth/',
            '/admin/ksiegowosc/companyinfo/add/',
            '/admin/ksiegowosc/companyinfo/',
            '/admin/logout/',
            '/admin/password_change/',
            '/health/',
            '/social-auth/',
            '/admin/jsi18n/',
        ]

    def __call__(self, request):
        # Sprawdź czy to jest żądanie, które wymaga sprawdzenia
        if self.should_check_company_info(request):
            # Sprawdź czy użytkownik ma dane firmy
            if not self.user_has_company_info(request.user):
                messages.warning(
                    request,
                    'Aby korzystać z systemu, musisz najpierw uzupełnić podstawowe dane swojej firmy.'
                )
                return redirect('admin:ksiegowosc_companyinfo_add')

        response = self.get_response(request)
        return response

    def should_check_company_info(self, request):
        """Sprawdza czy dla danego żądania trzeba sprawdzić dane firmy"""
        # Sprawdź czy użytkownik jest zalogowany
        if not request.user.is_authenticated:
            return False

        # Sprawdź czy to nie jest superuser (superuser może wszystko)
        if request.user.is_superuser:
            return False

        # Sprawdź czy ścieżka jest zwolniona
        path = request.path
        for exempt_path in self.exempt_paths:
            if path.startswith(exempt_path):
                return False

        # Sprawdź czy to żądanie AJAX - nie przekierowuj
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return False

        return True

    def user_has_company_info(self, user):
        """Sprawdza czy użytkownik ma uzupełnione podstawowe dane firmy"""
        try:
            company_info = CompanyInfo.objects.get(user=user)
            # Sprawdź czy wypełnione są podstawowe pola
            required_fields = ['company_name', 'tax_id', 'street', 'city', 'zip_code']
            for field in required_fields:
                if not getattr(company_info, field, '').strip():
                    return False
            return True
        except CompanyInfo.DoesNotExist:
            return False


class UserGroupMiddleware:
    """
    Middleware sprawdzający czy użytkownik należy do odpowiedniej grupy
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated and
            not request.user.is_superuser and
            request.path.startswith('/admin/') and
            not request.path.startswith('/admin/logout/')):

            # Sprawdź czy użytkownik należy do grupy ksiegowosc
            if not request.user.groups.filter(name='ksiegowosc').exists():
                messages.error(
                    request,
                    'Nie masz uprawnień do tej sekcji. Skontaktuj się z administratorem.'
                )
                return redirect('auth:login')

        response = self.get_response(request)
        return response
