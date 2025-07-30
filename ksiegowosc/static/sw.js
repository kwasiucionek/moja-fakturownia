// Service Worker dla Fakturownia PWA
const CACHE_NAME = 'fakturownia-v1.2.0';
const STATIC_CACHE_NAME = 'fakturownia-static-v1.2.0';
const DYNAMIC_CACHE_NAME = 'fakturownia-dynamic-v1.2.0';

// Zasoby do cache'owania podczas instalacji
const STATIC_ASSETS = [
  '/',
  '/auth/login/',
  '/admin/',
  '/admin/ksiegowosc/monthlysettlement/dashboard/',
  '/static/admin/css/base.css',
  '/static/admin/css/login.css',
  '/static/admin/js/core.js',
  '/static/admin/js/admin/RelatedObjectLookups.js',
  '/static/admin/js/jquery.init.js',
  '/static/admin/js/actions.js',
  '/static/jazzmin/css/adminlte.min.css',
  '/static/jazzmin/js/adminlte.min.js',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
  '/static/pwa/icons/icon-192x192.png',
  '/static/pwa/icons/icon-512x512.png',
  '/offline.html'
];

// Zasoby API do cache'owania dynamicznie
const API_CACHE_PATTERNS = [
  /\/admin\/ksiegowosc\/.*/,
  /\/auth\/.*/,
  /\/api\/.*/
];

// Strony dostępne offline
const OFFLINE_PAGES = [
  '/',
  '/auth/login/',
  '/admin/',
  '/admin/ksiegowosc/monthlysettlement/dashboard/'
];

// Instalacja Service Worker
self.addEventListener('install', event => {
  console.log('[SW] Instalacja Service Worker');
  
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then(cache => {
        console.log('[SW] Cache\'owanie zasobów statycznych');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('[SW] Instalacja zakończona pomyślnie');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('[SW] Błąd podczas instalacji:', error);
      })
  );
});

// Aktywacja Service Worker
self.addEventListener('activate', event => {
  console.log('[SW] Aktywacja Service Worker');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            if (cacheName !== STATIC_CACHE_NAME && cacheName !== DYNAMIC_CACHE_NAME) {
              console.log('[SW] Usuwanie starego cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('[SW] Aktywacja zakończona');
        return self.clients.claim();
      })
  );
});

// Przechwytywanie requestów
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  
  // Ignoruj requesty nie HTTP(S)
  if (!request.url.startsWith('http')) {
    return;
  }
  
  // Obsługa różnych typów requestów
  if (request.method === 'GET') {
    if (isStaticAsset(request.url)) {
      event.respondWith(handleStaticAsset(request));
    } else if (isAPIRequest(request.url)) {
      event.respondWith(handleAPIRequest(request));
    } else if (isPageRequest(request)) {
      event.respondWith(handlePageRequest(request));
    }
  } else {
    // POST, PUT, DELETE - zawsze próbuj wysłać do serwera
    event.respondWith(handleNonGetRequest(request));
  }
});

// Sprawdź czy to statyczny zasób
function isStaticAsset(url) {
  return url.includes('/static/') || 
         url.includes('/media/') ||
         url.includes('cdn.jsdelivr.net') ||
         url.includes('cdnjs.cloudflare.com') ||
         url.includes('fonts.googleapis.com') ||
         url.includes('fonts.gstatic.com');
}

// Sprawdź czy to request API
function isAPIRequest(url) {
  return API_CACHE_PATTERNS.some(pattern => pattern.test(url)) ||
         url.includes('/admin/jsi18n/') ||
         url.includes('/admin/autocomplete/');
}

// Sprawdź czy to request strony
function isPageRequest(request) {
  return request.headers.get('accept') && 
         request.headers.get('accept').includes('text/html');
}

// Obsługa statycznych zasobów (Cache First)
async function handleStaticAsset(request) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.error('[SW] Błąd obsługi statycznego zasobu:', error);
    
    // Zwróć cached response jeśli dostępny
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Fallback dla ikon
    if (request.url.includes('icon')) {
      return caches.match('/static/pwa/icons/icon-192x192.png');
    }
    
    throw error;
  }
}

// Obsługa requestów API (Network First)
async function handleAPIRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] API offline, próba pobrania z cache');
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Zwróć offline response dla API
    return new Response(
      JSON.stringify({
        error: 'Brak połączenia z internetem',
        offline: true,
        message: 'Dane mogą być nieaktualne'
      }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Obsługa stron (Network First z fallback)
async function handlePageRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Strona offline, próba pobrania z cache');
    
    // Spróbuj pobrać z cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Spróbuj pobrać podobną stronę z cache
    const url = new URL(request.url);
    for (const page of OFFLINE_PAGES) {
      if (url.pathname.startsWith(page)) {
        const fallbackResponse = await caches.match(page);
        if (fallbackResponse) {
          return fallbackResponse;
        }
      }
    }
    
    // Ostatnia szansa - strona offline
    const offlineResponse = await caches.match('/offline.html');
    if (offlineResponse) {
      return offlineResponse;
    }
    
    // Zwróć podstawową stronę offline
    return new Response(`
      <!DOCTYPE html>
      <html lang="pl">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Brak połączenia - Fakturownia</title>
        <style>
          body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            padding: 50px;
            background: #f8f9fa;
          }
          .offline-message {
            max-width: 500px;
            margin: 0 auto;
            padding: 30px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
          }
          .icon { font-size: 64px; color: #6c757d; margin-bottom: 20px; }
          h1 { color: #343a40; margin-bottom: 15px; }
          p { color: #6c757d; line-height: 1.6; }
          .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin-top: 20px;
          }
        </style>
      </head>
      <body>
        <div class="offline-message">
          <div class="icon">📡</div>
          <h1>Brak połączenia z internetem</h1>
          <p>Nie można załadować tej strony. Sprawdź połączenie internetowe i spróbuj ponownie.</p>
          <p>Niektóre funkcje mogą być dostępne offline.</p>
          <a href="/" class="btn">Spróbuj ponownie</a>
        </div>
        <script>
          // Auto-reload gdy połączenie wróci
          window.addEventListener('online', () => {
            window.location.reload();
          });
        </script>
      </body>
      </html>
    `, {
      status: 503,
      statusText: 'Service Unavailable',
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

// Obsługa requestów nie-GET (POST, PUT, DELETE)
async function handleNonGetRequest(request) {
  try {
    return await fetch(request);
  } catch (error) {
    console.error('[SW] Błąd podczas wysyłania danych:', error);
    
    // Tutaj można dodać kolejkę offline dla operacji CRUD
    // Na razie zwracamy błąd
    return new Response(
      JSON.stringify({
        error: 'Brak połączenia z internetem',
        message: 'Nie można wysłać danych. Spróbuj ponownie gdy połączenie wróci.',
        offline: true
      }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Obsługa wiadomości z aplikacji głównej
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CACHE_CLEAR') {
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => caches.delete(cacheName))
      );
    }).then(() => {
      event.ports[0].postMessage({ success: true });
    });
  }
  
  if (event.data && event.data.type === 'CACHE_STATUS') {
    caches.keys().then(cacheNames => {
      const totalSize = cacheNames.length;
      event.ports[0].postMessage({ 
        caches: cacheNames,
        totalCaches: totalSize 
      });
    });
  }
});

// Synchronizacja w tle (dla przyszłych funkcji)
self.addEventListener('sync', event => {
  if (event.tag === 'background-sync-invoices') {
    event.waitUntil(syncInvoices());
  }
});

async function syncInvoices() {
  console.log('[SW] Synchronizacja faktur w tle');
  // Tutaj będzie logika synchronizacji danych
}

// Push notifications (dla przyszłych funkcji)
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'Nowa wiadomość z Fakturowni',
    icon: '/static/pwa/icons/icon-192x192.png',
    badge: '/static/pwa/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'explore',
        title: 'Otwórz aplikację',
        icon: '/static/pwa/icons/checkmark.png'
      },
      {
        action: 'close',
        title: 'Zamknij',
        icon: '/static/pwa/icons/xmark.png'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('Fakturownia', options)
  );
});

// Obsługa kliknięć w powiadomienia
self.addEventListener('notificationclick', event => {
  event.notification.close();

  if (event.action === 'explore') {
    event.waitUntil(
      clients.openWindow('/admin/ksiegowosc/monthlysettlement/dashboard/')
    );
  }
});

console.log('[SW] Service Worker załadowany pomyślnie');