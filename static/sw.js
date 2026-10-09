const CACHE_NAME = 'anilog-v4';
const STATIC_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/images/placeholder.svg',
  '/static/images/logo.svg',
  '/static/images/favicon.svg',
];

// Install: pre-cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: purge old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategies
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;

  // Static assets: Cache-first, update in background
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        });
      }).catch(() => caches.match('/static/images/placeholder.svg'))
    );
    return;
  }

  // API: Network-first with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // Everything else: Network-first with cache fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});