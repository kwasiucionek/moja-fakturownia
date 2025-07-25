"""
URL configuration for fakturownia project - SECURITY HARDENED VERSION

The `urlpatterns` list routes URLs to views with enhanced security features.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import connection
from django.core.cache import cache
from django.middleware.csrf import get_token
from django_ratelimit.decorators import ratelimit
import logging
import time
import hashlib

logger = logging.getLogger(__name__)
security_logger = logging.getLogger('django.security')

# =============================================================================
# SECURITY UTILITIES
# =============================================================================

def log_security_event(request, event_type, details=""):
    """Loguj zdarzenia bezpieczeństwa"""
    client_ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
    
    security_logger.warning(
        f"SECURITY_EVENT: {event_type} | IP: {client_ip} | "
        f"User: {request.user if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous'} | "
        f"Path: {request.path} | Details: {details} | UA: {user_agent}"
    )

def get_client_ip(request):
    """Pobierz prawdziwy IP klienta"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip

def rate_limit_key(group, request):
    """Klucz dla rate limiting bazowany na IP"""
    return f"{group}:{get_client_ip(request)}"

# =============================================================================
# SECURITY MIDDLEWARE DECORATORS
# =============================================================================

def security_headers(view_func):
    """Dodaj dodatkowe nagłówki bezpieczeństwa"""
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        
        # Dodatkowe nagłówki bezpieczeństwa
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Cache control dla endpointów bezpieczeństwa
        if request.path.startswith('/health/') or request.path.startswith('/admin/'):
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        return response
    return wrapper

# =============================================================================
# ENHANCED HEALTH CHECK VIEWS
# =============================================================================

@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='60/m', method='GET', block=True)
@security_headers
@cache_page(60)
def health_check(request):
    """
    Kompleksowy health check endpoint z monitorowaniem bezpieczeństwa
    """
    start_time = time.time()
    
    try:
        status = {
            'status': 'healthy',
            'timestamp': int(time.time()),
            'version': getattr(settings, 'VERSION', 'unknown'),
            'environment': getattr(settings, 'ENVIRONMENT', 'unknown'),
            'checks': {
                'database': 'unknown',
                'cache': 'unknown',
                'disk_space': 'unknown',
                'memory': 'unknown',
            }
        }

        # Test bazy danych z timeoutem
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                if result and result[0] == 1:
                    status['checks']['database'] = 'healthy'
                else:
                    status['checks']['database'] = 'error'
                    status['status'] = 'unhealthy'
        except Exception as e:
            status['checks']['database'] = 'error'
            status['status'] = 'unhealthy'
            logger.error(f"Database health check failed: {e}")

        # Test cache
        try:
            cache_key = f'health_check_test_{int(time.time())}'
            test_value = 'test_value'
            cache.set(cache_key, test_value, 30)
            
            if cache.get(cache_key) == test_value:
                status['checks']['cache'] = 'healthy'
                cache.delete(cache_key)  # Cleanup
            else:
                status['checks']['cache'] = 'error'
                status['status'] = 'degraded'
        except Exception as e:
            status['checks']['cache'] = 'error'
            status['status'] = 'degraded'
            logger.warning(f"Cache health check failed: {e}")

        # Test przestrzeni dyskowej
        try:
            import shutil
            disk_usage = shutil.disk_usage(settings.BASE_DIR)
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            
            if disk_percent < 90:
                status['checks']['disk_space'] = 'healthy'
            elif disk_percent < 95:
                status['checks']['disk_space'] = 'warning'
                status['status'] = 'degraded'
            else:
                status['checks']['disk_space'] = 'critical'
                status['status'] = 'unhealthy'
                
            status['disk_usage_percent'] = round(disk_percent, 2)
            
        except Exception as e:
            status['checks']['disk_space'] = 'error'
            logger.warning(f"Disk space check failed: {e}")

        # Response time
        response_time = round((time.time() - start_time) * 1000, 2)
        status['response_time_ms'] = response_time
        
        if response_time > 5000:  # 5 sekund
            status['status'] = 'degraded'

        # HTTP status code
        http_status = 200
        if status['status'] == 'degraded':
            http_status = 200  # Pozostaw 200 dla degraded
        elif status['status'] == 'unhealthy':
            http_status = 503

        # Log slow health checks
        if response_time > 1000:  # Ponad 1 sekunda
            log_security_event(request, 'SLOW_HEALTH_CHECK', f"Response time: {response_time}ms")

        return JsonResponse(status, status=http_status)

    except Exception as e:
        logger.error(f"Health check critical failure: {e}")
        log_security_event(request, 'HEALTH_CHECK_FAILURE', str(e))
        
        return JsonResponse({
            'status': 'unhealthy',
            'timestamp': int(time.time()),
            'error': 'Health check failed',
            'response_time_ms': round((time.time() - start_time) * 1000, 2)
        }, status=503)


@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='30/m', method='GET', block=True)
@security_headers
def ready_check(request):
    """
    Readiness probe - sprawdza czy aplikacja jest gotowa do przyjmowania ruchu
    """
    try:
        from ksiegowosc.models import CompanyInfo
        
        # Test migracji i dostępności modeli
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ksiegowosc_companyinfo'"
                if 'sqlite' in settings.DATABASES['default']['ENGINE']
                else "SELECT tablename FROM pg_tables WHERE tablename='ksiegowosc_companyinfo'"
            )
            if not cursor.fetchone():
                raise Exception("Required tables not found")

        # Test podstawowej funkcjonalności
        CompanyInfo.objects.first()

        return HttpResponse("ready", content_type="text/plain", status=200)
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        log_security_event(request, 'READINESS_CHECK_FAILURE', str(e))
        return HttpResponse("not ready", content_type="text/plain", status=503)


@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='100/m', method='GET', block=True)
@security_headers
def live_check(request):
    """
    Liveness probe - minimalistyczny test czy aplikacja odpowiada
    """
    return HttpResponse("alive", content_type="text/plain", status=200)


@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='10/m', method='GET', block=True)
@security_headers
def metrics_endpoint(request):
    """
    Endpoint dla metryk (Prometheus format)
    """
    if not request.user.is_staff:
        log_security_event(request, 'UNAUTHORIZED_METRICS_ACCESS', f"User: {request.user}")
        raise Http404("Not found")
    
    try:
        from ksiegowosc.models import Invoice, Contractor
        
        metrics = []
        metrics.append('# HELP fakturownia_invoices_total Total number of invoices')
        metrics.append('# TYPE fakturownia_invoices_total counter')
        metrics.append(f'fakturownia_invoices_total {Invoice.objects.count()}')
        
        metrics.append('# HELP fakturownia_contractors_total Total number of contractors')
        metrics.append('# TYPE fakturownia_contractors_total counter')
        metrics.append(f'fakturownia_contractors_total {Contractor.objects.count()}')
        
        return HttpResponse('\n'.join(metrics), content_type='text/plain')
        
    except Exception as e:
        logger.error(f"Metrics endpoint failed: {e}")
        return HttpResponse("# Metrics unavailable", content_type='text/plain', status=500)

# =============================================================================
# SEO & SECURITY ENDPOINTS
# =============================================================================

@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='10/h', method='GET', block=True)
@security_headers
@cache_page(3600 * 24)  # Cache na 24 godziny
def robots_txt(request):
    """
    Dynamiczny robots.txt z dodatkowymi ścieżkami do blokowania
    """
    blocked_paths = [
        '/admin/',
        '/media/private/',
        '/api/',
        '/health/',
        '/metrics/',
        '/ready/',
        '/live/',
        '/.env',
        '/.git/',
        '/backup/',
        '/dumps/',
    ]
    
    content = "User-agent: *\n"
    for path in blocked_paths:
        content += f"Disallow: {path}\n"
    
    content += f"\nSitemap: {request.scheme}://{request.get_host()}/sitemap.xml\n"
    content += f"Crawl-delay: 10\n"  # Opóźnienie dla botów
    
    return HttpResponse(content, content_type="text/plain")


@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='5/h', method='GET', block=True)
@security_headers
@cache_page(3600 * 24)
def security_txt(request):
    """
    Security.txt zgodnie z RFC 9116
    """
    content = f"""Contact: mailto:security@{request.get_host()}
Expires: 2025-12-31T23:59:59Z
Preferred-Languages: pl, en
Policy: {request.scheme}://{request.get_host()}/security-policy
Hiring: {request.scheme}://{request.get_host()}/careers
"""
    
    return HttpResponse(content, content_type="text/plain")

# =============================================================================
# CSRF TOKEN ENDPOINT
# =============================================================================

@require_http_methods(["GET"])
@ratelimit(key=rate_limit_key, rate='30/m', method='GET', block=True)
@security_headers
def csrf_token_endpoint(request):
    """
    Endpoint do pobierania CSRF tokenu przez AJAX
    """
    token = get_token(request)
    return JsonResponse({'csrf_token': token})

# =============================================================================
# ADMIN HONEYPOT
# =============================================================================

@require_http_methods(["GET", "POST"])
@ratelimit(key=rate_limit_key, rate='3/h', method='ALL', block=True)
def admin_honeypot(request):
    """
    Honeypot dla domyślnego /admin/ - loguj próby dostępu
    """
    log_security_event(
        request, 
        'ADMIN_HONEYPOT_ACCESS', 
        f"Method: {request.method}, Path: {request.path}"
    )
    
    # Symuluj prawdziwy admin login page
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Django Administration</title></head>
    <body>
        <h1>Django Administration</h1>
        <p>Please enter your username and password.</p>
        <form method="post">
            <input type="text" name="username" placeholder="Username">
            <input type="password" name="password" placeholder="Password">
            <input type="submit" value="Log in">
        </form>
    </body>
    </html>
    """, content_type="text/html", status=200)

# =============================================================================
# URL PATTERNS
# =============================================================================

# Dynamiczna ścieżka admin z honeypot protection
admin_url = getattr(settings, 'ADMIN_URL', 'admin-secret-path-12345/')

urlpatterns = [
    # Honeypot dla domyślnego admin
    path('admin/', admin_honeypot, name='admin_honeypot'),
    
    # Prawdziwy admin panel
    path(admin_url, admin.site.urls),

    # Health checks z enhanced monitoring
    path('health/', health_check, name='health_check'),
    path('ready/', ready_check, name='ready_check'),
    path('live/', live_check, name='live_check'),
    path('metrics/', metrics_endpoint, name='metrics'),

    # Security & SEO endpoints
    path('robots.txt', robots_txt, name='robots_txt'),
    path('.well-known/security.txt', security_txt, name='security_txt'),
    path('security.txt', security_txt, name='security_txt_root'),

    # CSRF token dla AJAX
    path('csrf-token/', csrf_token_endpoint, name='csrf_token'),

    # Health check apps (szczegółowe)
    path('health/detailed/', include('health_check.urls')),

    # Authentication
    path('accounts/', include('allauth.urls')),
]

# =============================================================================
# DEBUG TOOLBAR (tylko w development)
# =============================================================================

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
    
    # Development test endpoints
    from django.views.generic import TemplateView
    urlpatterns += [
        path('test/', TemplateView.as_view(template_name='test.html'), name='test_page'),
        path('test-error/', lambda r: 1/0, name='test_error'),  # Test Sentry
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
    """Custom 404 page z logowaniem"""
    log_security_event(request, '404_ERROR', f"Path: {request.path}")
    
    from django.shortcuts import render
    return render(request, '404.html', {
        'request_path': request.path,
    }, status=404)

def custom_500(request):
    """Custom 500 page z logowaniem"""
    log_security_event(request, '500_ERROR', f"Path: {request.path}")
    
    from django.shortcuts import render
    return render(request, '500.html', status=500)

def custom_403(request, exception):
    """Custom 403 page z logowaniem"""
    log_security_event(request, '403_ERROR', f"Path: {request.path}")
    
    from django.shortcuts import render
    return render(request, '403.html', status=403)

def custom_400(request, exception):
    """Custom 400 page z logowaniem"""
    log_security_event(request, '400_ERROR', f"Path: {request.path}")
    
    from django.shortcuts import render
    return render(request, '400.html', status=400)

def custom_429(request, exception):
    """Rate limit exceeded"""
    log_security_event(request, 'RATE_LIMIT_EXCEEDED', f"Path: {request.path}")
    
    from django.shortcuts import render
    return render(request, '429.html', status=429)

# Przypisz custom error handlers
handler404 = custom_404
handler500 = custom_500
handler403 = custom_403
handler400 = custom_400

# =============================================================================
# ADMIN CUSTOMIZATION
# =============================================================================

admin.site.site_header = "Fakturownia - Panel Administracyjny"
admin.site.site_title = "Fakturownia Admin"
admin.site.index_title = "Zarządzanie Fakturownią"

# =============================================================================
# API ENDPOINTS (przyszłe rozszerzenia)
# =============================================================================

api_patterns = [
    # path('invoices/', include('ksiegowosc.api.urls')),
    # path('auth/', include('ksiegowosc.api.auth_urls')),
]

if getattr(settings, 'ENABLE_API', False):
    urlpatterns += [
        path('api/v1/', include(api_patterns)),
    ]

# =============================================================================
# SECURITY MIDDLEWARE INTEGRATION
# =============================================================================

# Rate limiting dla całej aplikacji
from django_ratelimit.exceptions import Ratelimited

def ratelimited_error(request, exception):
    """Handler dla rate limit errors"""
    log_security_event(request, 'RATE_LIMITED', f"Path: {request.path}")
    from django.shortcuts import render
    return render(request, '429.html', status=429)

# =============================================================================
# WEBHOOK ENDPOINTS (dla zewnętrznych integracji)
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key=rate_limit_key, rate='100/h', method='POST', block=True)
def webhook_handler(request, webhook_type):
    """
    Bezpieczny handler dla webhooków
    """
    # Weryfikacja podpisu (implementuj zgodnie z dostawcą)
    signature = request.META.get('HTTP_X_SIGNATURE', '')
    
    if not signature:
        log_security_event(request, 'WEBHOOK_NO_SIGNATURE', f"Type: {webhook_type}")
        return HttpResponse("Unauthorized", status=401)
    
    # TODO: Implementuj weryfikację podpisu
    
    log_security_event(request, 'WEBHOOK_RECEIVED', f"Type: {webhook_type}")
    
    return JsonResponse({'status': 'received'})

# Dodaj webhook endpoints
urlpatterns += [
    path('webhooks/<str:webhook_type>/', webhook_handler, name='webhook_handler'),
]

# =============================================================================
# FINAL SECURITY VALIDATIONS
# =============================================================================

# Sprawdź czy admin URL nie jest domyślny w produkcji
if not settings.DEBUG and admin_url == 'admin/':
    logger.warning("SECURITY WARNING: Using default admin URL in production!")

# Sprawdź czy SECRET_KEY nie jest domyślny
if 'django-insecure' in settings.SECRET_KEY:
    logger.critical("CRITICAL: Using default SECRET_KEY in production!")

# Log startup security info
if not settings.DEBUG:
    security_logger.info(f"Fakturownia started with admin URL: /{admin_url}")
    security_logger.info(f"Security features enabled: SSL={settings.SECURE_SSL_REDIRECT}, "
                        f"HSTS={settings.SECURE_HSTS_SECONDS}, "
                        f"Rate Limiting={getattr(settings, 'RATELIMIT_ENABLE', True)}")
