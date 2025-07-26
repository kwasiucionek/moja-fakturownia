"""
URL configuration for fakturownia project - PRODUCTION VERSION

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse, HttpResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.db import connection
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# HEALTH CHECK VIEWS
# =============================================================================

@require_http_methods(["GET"])
@cache_page(60)  # Cache na 1 minutę
def health_check(request):
    """
    Podstawowy health check endpoint
    Sprawdza status aplikacji, bazy danych i cache
    """
    try:
        status = {
            'status': 'healthy',
            'database': 'unknown',
            'cache': 'unknown',
        }
        
        # Test bazy danych
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                status['database'] = 'connected'
        except Exception as e:
            status['database'] = 'error'
            status['status'] = 'unhealthy'
            logger.error(f"Database health check failed: {e}")
        
        # Test cache
        try:
            cache_key = 'health_check_test'
            cache.set(cache_key, 'test', 30)
            if cache.get(cache_key) == 'test':
                status['cache'] = 'working'
            else:
                status['cache'] = 'error'
                status['status'] = 'degraded'
        except Exception as e:
            status['cache'] = 'error'
            status['status'] = 'degraded'
            logger.warning(f"Cache health check failed: {e}")
        
        # HTTP status code na podstawie statusu
        http_status = 200 if status['status'] == 'healthy' else 503
        
        return JsonResponse(status, status=http_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e) if settings.DEBUG else 'Internal server error'
        }, status=503)


@require_http_methods(["GET"])
def ready_check(request):
    """
    Readiness probe - sprawdza czy aplikacja jest gotowa do przyjmowania ruchu
    """
    try:
        # Sprawdź kluczowe komponenty
        from ksiegowosc.models import CompanyInfo
        
        # Test modelu (czy migracje zostały wykonane)
        CompanyInfo.objects.first()
        
        return HttpResponse("ready", content_type="text/plain", status=200)
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return HttpResponse("not ready", content_type="text/plain", status=503)


@require_http_methods(["GET"])
def live_check(request):
    """
    Liveness probe - sprawdza czy aplikacja żyje
    """
    return HttpResponse("alive", content_type="text/plain", status=200)


# =============================================================================
# ROBOTS.TXT
# =============================================================================

@require_http_methods(["GET"])
@cache_page(3600 * 24)  # Cache na 24 godziny
def robots_txt(request):
    """
    Dynamiczny robots.txt
    """
    content = """User-agent: *
Disallow: /admin/
Disallow: /media/private/
Disallow: /api/
Allow: /

Sitemap: {protocol}://{domain}/sitemap.xml
""".format(
        protocol='https' if request.is_secure() else 'http',
        domain=request.get_host()
    )
    
    return HttpResponse(content, content_type="text/plain")


# =============================================================================
# URL PATTERNS
# =============================================================================

# Dynamiczna ścieżka admin (bezpieczeństwo)
admin_url = getattr(settings, 'ADMIN_URL', 'admin/')

urlpatterns = [
    # Admin panel
    path(admin_url, admin.site.urls),
    
    # Health checks
    path('health/', health_check, name='health_check'),
    path('ready/', ready_check, name='ready_check'),
    path('live/', live_check, name='live_check'),
    
    # SEO
    path('robots.txt', robots_txt, name='robots_txt'),
    
    # Health check apps (jeśli zainstalowane)
    path('health/', include('health_check.urls')),
]

# =============================================================================
# DEBUG TOOLBAR (tylko w development)
# =============================================================================

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]

# =============================================================================
# STATIC & MEDIA FILES (tylko w development)
# =============================================================================

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# =============================================================================
# ERROR HANDLERS
# =============================================================================

def custom_404(request, exception):
    """Custom 404 page"""
    from django.shortcuts import render
    return render(request, '404.html', status=404)

def custom_500(request):
    """Custom 500 page"""
    from django.shortcuts import render
    return render(request, '500.html', status=500)

def custom_403(request, exception):
    """Custom 403 page"""
    from django.shortcuts import render
    return render(request, '403.html', status=403)

# Przypisz custom error handlers
handler404 = custom_404
handler500 = custom_500
handler403 = custom_403

# =============================================================================
# ADMIN CUSTOMIZATION
# =============================================================================

# Customizacja admin site
admin.site.site_header = "Fakturownia - Panel Administracyjny"
admin.site.site_title = "Fakturownia Admin"
admin.site.index_title = "Zarządzanie Fakturownią"

# =============================================================================
# API ENDPOINTS (przyszłe rozszerzenia)
# =============================================================================

# Placeholder dla przyszłych API endpoints
api_patterns = [
    # path('invoices/', include('ksiegowosc.api.urls')),
]

if getattr(settings, 'ENABLE_API', False):
    urlpatterns += [
        path('api/v1/', include(api_patterns)),
    ]

# =============================================================================
# SECURITY HEADERS MIDDLEWARE BYPASS
# =============================================================================

# Dodaj X-Content-Type-Options dla health checks
from django.utils.decorators import decorator_from_middleware
from django.middleware.security import SecurityMiddleware

# =============================================================================
# DEVELOPMENT ONLY ENDPOINTS
# =============================================================================

if settings.DEBUG:
    from django.views.generic import TemplateView
    
    # Test page for development
    urlpatterns += [
        path('test/', TemplateView.as_view(template_name='test.html'), name='test_page'),
    ]