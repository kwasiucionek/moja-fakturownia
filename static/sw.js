// Enhanced Service Worker dla Fakturownia PWA v1.2.0
const CACHE_NAME = 'fakturownia-v1.2.0';
const STATIC_CACHE = 'fakturownia-static-v1.2.0';
const DYNAMIC_CACHE = 'fakturownia-dynamic-v1.2.0';
const API_CACHE = 'fakturownia-api-v1.2.0';

// Kluczowe zasoby do cache'owania podczas instalacji
const CRITICAL_RESOURCES = [
  '/',
  '/auth/login/',
  '/admin/',
  '/admin/ksiegowosc/monthlysettlement/dashboard/',
  '/offline.html',
  '/static/jazzmin/css/adminlte.min.css',
  '/static/jazzmin/js/adminlte.min.js',
  '/static/admin/js/vendor/jquery/jquery.js',
  '/static/pwa/icons/icon-192x192.png',
  '/static/pwa/icons/icon-512x512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
];

// API endpoints do cache'owania
const API_ENDPOINTS = [
  '/admin/ksiegowosc/',
  '/api/',
  '/pwa/api/'
];

// Strategia cache dla różnych typów zasobów
const CACHE_STRATEGIES = {
  static: 'cache-first',
  api: 'network-first', 
  pages: 'network-first',
  images: 'cache-first'
};

// Czas życia cache (w sekundach)
const CACHE_EXPIRY = {
  static: 30 * 24 * 60 * 60, // 30 dni
  api: 5 * 60,               // 5 minut
  pages: 24 * 60 * 60,       // 24 godziny
  images: 7 * 24 * 60 * 60   // 7 dni
};

// Instalacja Service Worker
self.addEventListener('install', event => {
  console.log('[SW] Instalowanie Service Worker v1.2.0');
  
  event.waitUntil(
    Promise.all([
      // Cache kluczowych zasobów
      caches.open(STATIC_CACHE).then(cache => {
        console.log('[SW] Cache\'owanie kluczowych zasobów');
        return cache.addAll(CRITICAL_RESOURCES.map(url => new Request(url, {cache: 'no-cache'})));
      }),
      
      // Wymuś aktywację nowego SW
      self.skipWaiting()
    ]).catch(error => {
      console.error('[SW] Błąd podczas instalacji:', error);
    })
  );
});

// Aktywacja Service Worker
self.addEventListener('activate', event => {
  console.log('[SW] Aktywacja Service Worker v1.2.0');
  
  event.waitUntil(
    Promise.all([
      // Usuń stare cache
      cleanupOldCaches(),
      
      // Przejmij kontrolę nad wszystkimi klientami
      self.clients.claim()
    ])
  );
});

// Czyszczenie starych cache'ów
async function cleanupOldCaches() {
  const cacheNames = await caches.keys();
  const validCaches = [STATIC_CACHE, DYNAMIC_CACHE, API_CACHE];
  
  return Promise.all(
    cacheNames.map(cacheName => {
      if (!validCaches.includes(cacheName)) {
        console.log('[SW] Usuwanie starego cache:', cacheName);
        return caches.delete(cacheName);
      }
    })
  );
}

// Główna obsługa requestów
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  
  // Ignoruj requesty nie-HTTP
  if (!request.url.startsWith('http')) {
    return;
  }
  
  // Ignoruj requesty z innych domen (oprócz CDN)
  if (url.origin !== self.location.origin && !isTrustedDomain(url.hostname)) {
    return;
  }
  
  // Wybierz strategię na podstawie typu zasobu
  if (request.method === 'GET') {
    if (isStaticResource(request.url)) {
      event.respondWith(handleStaticResource(request));
    } else if (isAPIRequest(request.url)) {
      event.respondWith(handleAPIRequest(request));
    } else if (isPageRequest(request)) {
      event.respondWith(handlePageRequest(request));
    } else if (isImageRequest(request.url)) {
      event.respondWith(handleImageRequest(request));
    }
  } else {
    // POST, PUT, DELETE - network only z fallback
    event.respondWith(handleMutationRequest(request));
  }
});

// Sprawdzanie typów zasobów
function isStaticResource(url) {
  return url.includes('/static/') || 
         url.includes('cdnjs.cloudflare.com') ||
         url.includes('fonts.googleapis.com') ||
         url.includes('fonts.gstatic.com');
}

function isAPIRequest(url) {
  return API_ENDPOINTS.some(endpoint => url.includes(endpoint)) ||
         url.includes('/admin/jsi18n/') ||
         url.includes('/autocomplete/');
}

function isPageRequest(request) {
  return request.headers.get('accept') && 
         request.headers.get('accept').includes('text/html');
}

function isImageRequest(url) {
  return /\.(jpg|jpeg|png|gif|webp|svg|ico)(\?.*)?$/i.test(url);
}

function isTrustedDomain(hostname) {
  const trustedDomains = [
    'cdnjs.cloudflare.com',
    'fonts.googleapis.com', 
    'fonts.gstatic.com',
    'cdn.jsdelivr.net'
  ];
  return trustedDomains.includes(hostname);
}

// Cache First Strategy - dla zasobów statycznych
async function handleStaticResource(request) {
  try {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse && !isExpired(cachedResponse)) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      const responseClone = networkResponse.clone();
      responseClone.headers.set('sw-cache-timestamp', Date.now().toString());
      cache.put(request, responseClone);
    }
    
    return networkResponse;
    
  } catch (error) {
    console.log('[SW] Błąd zasobu statycznego, próba cache:', error.message);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Fallback dla krytycznych zasobów
    if (request.url.includes('icon')) {
      return caches.match('/static/pwa/icons/icon-192x192.png');
    }
    
    throw error;
  }
}

// Network First Strategy - dla API
async function handleAPIRequest(request) {
  try {
    const networkResponse = await fetch(request, {
      headers: { ...request.headers, 'Cache-Control': 'no-cache' }
    });
    
    if (networkResponse.ok) {
      const cache = await caches.open(API_CACHE);
      const responseClone = networkResponse.clone();
      responseClone.headers.set('sw-cache-timestamp', Date.now().toString());
      cache.put(request, responseClone);
    }
    
    return networkResponse;
    
  } catch (error) {
    console.log('[SW] API offline, próba cache:', error.message);
    
    const cachedResponse = await caches.match(request);
    if (cachedResponse && !isExpired(cachedResponse, 'api')) {
      // Dodaj header oznaczający dane z cache
      const modifiedResponse = new Response(cachedResponse.body, {
        status: cachedResponse.status,
        statusText: cachedResponse.statusText,
        headers: {
          ...cachedResponse.headers,
          'X-Cache-Status': 'cached',
          'X-Cache-Warning': 'Dane mogą być nieaktualne'
        }
      });
      return modifiedResponse;
    }
    
    // Fallback response dla API
    return new Response(
      JSON.stringify({
        error: 'Brak połączenia z internetem',
        offline: true,
        message: 'Aplikacja pracuje w trybie offline'
      }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 
          'Content-Type': 'application/json',
          'X-Cache-Status': 'offline'
        }
      }
    );
  }
}

// Network First Strategy - dla stron HTML
async function handlePageRequest(request) {
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
    
  } catch (error) {
    console.log('[SW] Strona offline, próba cache:', error.message);
    
    // Spróbuj cache dla tej konkretnej strony
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Spróbuj podobną stronę (np. dashboard dla admin/)
    const url = new URL(request.url);
    const fallbackPages = [
      '/admin/ksiegowosc/monthlysettlement/dashboard/',
      '/admin/',
      '/'
    ];
    
    for (const fallbackUrl of fallbackPages) {
      if (url.pathname.startsWith(fallbackUrl.slice(0, -1))) {
        const fallbackResponse = await caches.match(fallbackUrl);
        if (fallbackResponse) {
          return fallbackResponse;
        }
      }
    }
    
    // Ostateczny fallback - strona offline
    const offlineResponse = await caches.match('/offline.html');
    if (offlineResponse) {
      return offlineResponse;
    }
    
    // Jeśli nawet offline.html nie jest dostępne, zwróć podstawową stronę
    return createOfflinePageResponse();
  }
}

// Cache First Strategy - dla obrazów
async function handleImageRequest(request) {
  try {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse && !isExpired(cachedResponse, 'images')) {
      return cachedResponse;
    }
    
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
    
  } catch (error) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Fallback image
    return caches.match('/static/pwa/icons/icon-192x192.png');
  }
}

// Network Only dla mutacji (POST, PUT, DELETE)
async function handleMutationRequest(request) {
  try {
    return await fetch(request);
  } catch (error) {
    console.error('[SW] Błąd mutacji:', error.message);
    
    // Tu można dodać kolejkę offline dla synchronizacji
    return new Response(
      JSON.stringify({
        error: 'Brak połączenia z internetem',
        message: 'Operacja zostanie powtórzona gdy połączenie wróci',
        offline: true,
        retry: true
      }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Sprawdzanie czy response jest expired
function isExpired(response, type = 'static') {
  const timestamp = response.headers.get('sw-cache-timestamp');
  if (!timestamp) return false;
  
  const age = (Date.now() - parseInt(timestamp)) / 1000;
  return age > CACHE_EXPIRY[type];
}

// Utworzenie podstawowej strony offline
function createOfflinePageResponse() {
  const html = `
    <!DOCTYPE html>
    <html lang="pl">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Brak połączenia - Fakturownia</title>
      <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa; }
        .container { max-width: 500px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .icon { font-size: 64px; margin-bottom: 20px; }
        h1 { color: #343a40; margin-bottom: 15px; }
        p { color: #6c757d; line-height: 1.6; }
        .btn { display: inline-block; padding: 12px 24px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="icon">📡</div>
        <h1>Brak połączenia z internetem</h1>
        <p>Nie można załadować tej strony. Sprawdź połączenie internetowe i spróbuj ponownie.</p>
        <a href="/" class="btn" onclick="window.location.reload()">Spróbuj ponownie</a>
      </div>
      <script>
        window.addEventListener('online', () => window.location.reload());
      </script>
    </body>
    </html>
  `;
  
  return new Response(html, {
    status: 503,
    statusText: 'Service Unavailable',
    headers: { 'Content-Type': 'text/html; charset=utf-8' }
  });
}

// Obsługa wiadomości z aplikacji głównej
self.addEventListener('message', event => {
  const { type, data } = event.data || {};
  
  switch (type) {
    case 'SKIP_WAITING':
      self.skipWaiting();
      break;
      
    case 'CACHE_CLEAR':
      clearAllCaches().then(() => {
        event.ports[0]?.postMessage({ success: true });
      });
      break;
      
    case 'CACHE_STATUS':
      getCacheStatus().then(status => {
        event.ports[0]?.postMessage(status);
      });
      break;
      
    case 'FORCE_UPDATE':
      self.registration.update();
      break;
  }
});

// Czyszczenie wszystkich cache'ów
async function clearAllCaches() {
  const cacheNames = await caches.keys();
  return Promise.all(cacheNames.map(name => caches.delete(name)));
}

// Status cache'ów
async function getCacheStatus() {
  const cacheNames = await caches.keys();
  const status = {};
  
  for (const name of cacheNames) {
    const cache = await caches.open(name);
    const keys = await cache.keys();
    status[name] = keys.length;
  }
  
  return status;
}

// Background Sync (dla przyszłych funkcji)
self.addEventListener('sync', event => {
  switch (event.tag) {
    case 'sync-invoices':
      event.waitUntil(syncInvoices());
      break;
    case 'sync-payments':
      event.waitUntil(syncPayments());
      break;
  }
});

async function syncInvoices() {
  console.log('[SW] Synchronizacja faktur w tle');
  // Implementacja synchronizacji faktur
}

async function syncPayments() {
  console.log('[SW] Synchronizacja płatności w tle');
  // Implementacja synchronizacji płatności
}

// Push Notifications
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'Nowa wiadomość z Fakturowni',
    icon: '/static/pwa/icons/icon-192x192.png',
    badge: '/static/pwa/icons/badge-72x72.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: '1'
    },
    actions: [
      {
        action: 'explore',
        title: 'Otwórz',
        icon: '/static/pwa/icons/checkmark.png'
      },
      {
        action: 'close',
        title: 'Zamknij',
        icon: '/static/pwa/icons/xmark.png'
      }
    ],
    requireInteraction: true,
    tag: 'fakturownia-notification'
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
  } else if (event.action === 'close') {
    // Zamknij powiadomienie
  } else {
    // Domyślna akcja - otwórz aplikację
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

console.log('[SW] Enhanced Service Worker v1.2.0 załadowany pomyślnie');