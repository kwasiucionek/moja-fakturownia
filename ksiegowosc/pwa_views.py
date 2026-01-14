# ksiegowosc/pwa_views.py

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
import os


@cache_page(60 * 60 * 24)  # Cache na 24 godziny
@require_http_methods(["GET"])
def pwa_manifest(request):
    """Generuje dynamiczny manifest.json dla PWA"""
    
    # Pobierz bazowy URL
    base_url = request.build_absolute_uri('/').rstrip('/')
    
    manifest = {
        "name": "Fakturownia - System Księgowy",
        "short_name": "Fakturownia",
        "description": "System księgowy dla małych przedsiębiorców - faktury, rozliczenia, ZUS",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#007bff",
        "orientation": "portrait-primary",
        "scope": "/",
        "lang": "pl",
        "categories": ["business", "finance", "productivity"],
        "icons": [
            {
                "src": f"{base_url}/static/pwa/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": f"{base_url}/static/pwa/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable any"
            }
        ],
        "shortcuts": [],
        "related_applications": [],
        "prefer_related_applications": False,
        "edge_side_panel": {
            "preferred_width": 400
        },
        "launch_handler": {
            "client_mode": "navigate-existing"
        }
    }
    
    # Dodaj shortcuts tylko dla zalogowanych użytkowników
    if request.user.is_authenticated:
        shortcuts = [
            {
                "name": "Nowa faktura",
                "short_name": "Faktura",
                "description": "Utwórz nową fakturę sprzedaży",
                "url": "/admin/ksiegowosc/invoice/add/",
                "icons": [
                    {
                        "src": f"{base_url}/static/pwa/icons/shortcut-invoice.png",
                        "sizes": "96x96"
                    }
                ]
            },
            {
                "name": "Dashboard",
                "short_name": "Panel",
                "description": "Przejdź do dashboardu",
                "url": "/admin/ksiegowosc/monthlysettlement/dashboard/",
                "icons": [
                    {
                        "src": f"{base_url}/static/pwa/icons/shortcut-dashboard.png",
                        "sizes": "96x96"
                    }
                ]
            },
            {
                "name": "Rozliczenie miesięczne",
                "short_name": "Rozliczenie",
                "description": "Oblicz rozliczenie miesięczne",
                "url": "/admin/ksiegowosc/monthlysettlement/oblicz/",
                "icons": [
                    {
                        "src": f"{base_url}/static/pwa/icons/shortcut-settlement.png",
                        "sizes": "96x96"
                    }
                ]
            },
            {
                "name": "Kalkulator ZUS",
                "short_name": "ZUS",
                "description": "Kalkulator składek ZUS",
                "url": "/admin/ksiegowosc/monthlysettlement/kalkulator-zus/",
                "icons": [
                    {
                        "src": f"{base_url}/static/pwa/icons/shortcut-zus.png",
                        "sizes": "96x96"
                    }
                ]
            }
        ]
        manifest["shortcuts"] = shortcuts
    
    response = JsonResponse(manifest, json_dumps_params={'indent': 2})
    response['Content-Type'] = 'application/manifest+json'
    response['Cache-Control'] = 'public, max-age=86400'  # 24 godziny
    
    return response


@cache_page(60 * 60)  # Cache na 1 godzinę
@require_http_methods(["GET"])
def service_worker(request):
    """Serwuje service worker"""
    
    # Wczytaj service worker z pliku
    sw_path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR, 'sw.js')
    
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()
    except FileNotFoundError:
        # Fallback - podstawowy service worker
        sw_content = """
console.log('Service Worker loaded - basic version');

const CACHE_NAME = 'fakturownia-basic-v1.0.0';

self.addEventListener('install', event => {
    console.log('Service Worker installing...');
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('Service Worker activating...');
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
    // Basic fetch handling
    if (event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request).catch(() => {
                if (event.request.headers.get('accept').includes('text/html')) {
                    return new Response(
                        '<h1>Brak połączenia</h1><p>Sprawdź połączenie internetowe.</p>',
                        { headers: { 'Content-Type': 'text/html' } }
                    );
                }
                return new Response('Offline', { status: 503 });
            })
        );
    }
});
        """
    
    response = HttpResponse(sw_content, content_type='application/javascript')
    response['Cache-Control'] = 'public, max-age=3600'  # 1 godzina
    response['Service-Worker-Allowed'] = '/'
    
    return response


@require_http_methods(["GET"])
def offline_page(request):
    """Strona offline dla PWA"""
    
    context = {
        'title': 'Brak połączenia - Fakturownia',
        'user': request.user,
    }
    
    return render(request, 'pwa/offline.html', context, status=503)


@cache_page(60 * 60 * 24)  # Cache na 24 godziny
@require_http_methods(["GET"])
def pwa_browserconfig(request):
    """Generuje browserconfig.xml dla Windows/IE"""
    
    base_url = request.build_absolute_uri('/').rstrip('/')
    
    browserconfig = f'''<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
    <msapplication>
        <tile>
            <square70x70logo src="{base_url}/static/pwa/icons/mstile-70x70.png"/>
            <square150x150logo src="{base_url}/static/pwa/icons/mstile-150x150.png"/>
            <square310x310logo src="{base_url}/static/pwa/icons/mstile-310x310.png"/>
            <wide310x150logo src="{base_url}/static/pwa/icons/mstile-310x150.png"/>
            <TileColor>#007bff</TileColor>
        </tile>
    </msapplication>
</browserconfig>'''
    
    response = HttpResponse(browserconfig, content_type='application/xml')
    response['Cache-Control'] = 'public, max-age=86400'  # 24 godziny
    
    return response


@login_required
@require_http_methods(["GET"])
def pwa_status(request):
    """API endpoint dla statusu PWA"""
    
    status = {
        'pwa_enabled': True,
        'user_authenticated': request.user.is_authenticated,
        'username': request.user.username if request.user.is_authenticated else None,
        'server_time': timezone.now().isoformat(),
        'features': {
            'offline_support': True,
            'push_notifications': False,  # Można włączyć w przyszłości
            'background_sync': False,     # Można włączyć w przyszłości
            'shortcuts': request.user.is_authenticated,
            'install_prompt': True,
        },
        'cache_info': {
            'version': '1.2.0',
            'last_updated': timezone.now().isoformat(),
        }
    }
    
    return JsonResponse(status)


@login_required
@require_http_methods(["POST"])
def pwa_install_tracking(request):
    """Tracking instalacji PWA"""
    
    try:
        data = json.loads(request.body)
        event_type = data.get('event_type')  # 'prompt_shown', 'installed', 'dismissed'
        platform = data.get('platform', 'unknown')
        
        # Tutaj można dodać logowanie do bazy danych lub analytics
        
        return JsonResponse({
            'status': 'success',
            'message': f'Event {event_type} tracked successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@require_http_methods(["GET"])
def pwa_update_check(request):
    """Sprawdza dostępność aktualizacji PWA"""
    
    # Wersja aplikacji - można pobierać z settings lub pliku
    current_version = getattr(settings, 'PWA_VERSION', '1.2.0')
    
    # Tutaj można dodać logikę sprawdzania aktualizacji
    # Na przykład porównanie z wersją w repozytorium lub API
    
    update_info = {
        'current_version': current_version,
        'latest_version': current_version,  # Na razie ta sama
        'update_available': False,
        'update_required': False,
        'release_notes': [],
        'download_size': None,
    }
    
    response = JsonResponse(update_info)
    response['Cache-Control'] = 'no-cache'  # Zawsze sprawdzaj aktualność
    
    return response


@login_required
@require_http_methods(["GET"])
def pwa_shortcuts_api(request):
    """API dla dynamicznych shortcuts"""
    
    shortcuts = [
        {
            'id': 'new_invoice',
            'name': 'Nowa faktura',
            'url': '/admin/ksiegowosc/invoice/add/',
            'icon': '📄',
            'description': 'Utwórz nową fakturę sprzedaży'
        },
        {
            'id': 'dashboard',
            'name': 'Dashboard',
            'url': '/admin/ksiegowosc/monthlysettlement/dashboard/',
            'icon': '📊',
            'description': 'Przejdź do dashboardu z wykresami'
        },
        {
            'id': 'settlement',
            'name': 'Rozliczenie',
            'url': '/admin/ksiegowosc/monthlysettlement/oblicz/',
            'icon': '🧮',
            'description': 'Oblicz rozliczenie miesięczne'
        },
        {
            'id': 'zus_calculator',
            'name': 'Kalkulator ZUS',
            'url': '/admin/ksiegowosc/monthlysettlement/kalkulator-zus/',
            'icon': '💰',
            'description': 'Kalkulator składek ZUS'
        },
        {
            'id': 'add_payment',
            'name': 'Dodaj płatność',
            'url': '/admin/ksiegowosc/payment/add/',
            'icon': '💳',
            'description': 'Zarejestruj nową płatność'
        }
    ]
    
    return JsonResponse({
        'shortcuts': shortcuts,
        'timestamp': timezone.now().isoformat()
    })


@require_http_methods(["GET"])
def pwa_health_check(request):
    """Health check dla PWA"""
    
    health_status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'version': getattr(settings, 'PWA_VERSION', '1.2.0'),
        'services': {
            'database': 'healthy',
            'cache': 'healthy',
            'static_files': 'healthy'
        }
    }
    
    # Sprawdź bazę danych
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['services']['database'] = 'healthy'
    except Exception:
        health_status['services']['database'] = 'unhealthy'
        health_status['status'] = 'degraded'
    
    # Sprawdź cache
    try:
        from django.core.cache import cache
        cache.set('health_check', 'test', 30)
        if cache.get('health_check') == 'test':
            health_status['services']['cache'] = 'healthy'
        else:
            health_status['services']['cache'] = 'unhealthy'
            health_status['status'] = 'degraded'
    except Exception:
        health_status['services']['cache'] = 'unhealthy'
        health_status['status'] = 'degraded'
    
    # Status code na podstawie zdrowia
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return JsonResponse(health_status, status=status_code)