# ksiegowosc/pwa_urls.py

from django.urls import path
from . import pwa_views

app_name = 'pwa'

urlpatterns = [
    # Podstawowe pliki PWA
    path('manifest.json', pwa_views.pwa_manifest, name='pwa_manifest'),
    path('sw.js', pwa_views.service_worker, name='service_worker'),
    path('offline.html', pwa_views.offline_page, name='offline_page'),
    path('browserconfig.xml', pwa_views.pwa_browserconfig, name='browserconfig'),

    # API endpoints dla PWA
    path('api/status/', pwa_views.pwa_status, name='pwa_status'),
    path('api/install-tracking/', pwa_views.pwa_install_tracking, name='install_tracking'),
    path('api/update-check/', pwa_views.pwa_update_check, name='update_check'),
    path('api/shortcuts/', pwa_views.pwa_shortcuts_api, name='shortcuts_api'),

    # Health check
    path('health/', pwa_views.pwa_health_check, name='health_check'),
]
