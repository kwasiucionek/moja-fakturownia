# ksiegowosc/middleware.py

from django.shortcuts import redirect
from django.urls import reverse
from .models import CompanyInfo
import logging

logger = logging.getLogger(__name__)


class AdminLoginRedirectMiddleware:
    """
    Middleware przekierowujący użytkowników bez danych firmy
    do formularza uzupełnienia CompanyInfo.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Ścieżki zwolnione ze sprawdzania
        self.exempt_prefixes = [
            '/static/',
            '/media/',
            '/__debug__/',
            '/health/',
            '/auth/',
            '/admin/logout/',
            '/admin/jsi18n/',
            '/admin/ksiegowosc/companyinfo/',  # KLUCZOWE - cała ścieżka companyinfo
        ]

    def __call__(self, request):
        # Sprawdź czy użytkownik istnieje i jest zalogowany
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        # Superuser może wszystko
        if request.user.is_superuser:
            return self.get_response(request)

        path = request.path

        # Sprawdź czy ścieżka jest zwolniona
        for prefix in self.exempt_prefixes:
            if path.startswith(prefix):
                return self.get_response(request)

        # Sprawdź czy to żądanie AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return self.get_response(request)

        # Sprawdź czy użytkownik ma profil firmy
        has_company = CompanyInfo.objects.filter(user=request.user).exists()

        if not has_company:
            logger.debug(f"User {request.user.username} has no CompanyInfo, redirecting from {path}")
            return redirect('admin:ksiegowosc_companyinfo_add')

        return self.get_response(request)
