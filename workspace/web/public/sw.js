const CACHE = 'cardex-v1';
const SHELL = ['/', '/index.html'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // API: network-first, fall back to cache (only cache GET — never POST/PUT/PATCH).
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          if (res.ok && request.method === 'GET') {
            caches.open(CACHE).then((c) => c.put(request, clone));
          }
          return res;
        })
        .catch(() => (request.method === 'GET' ? caches.match(request) : Promise.reject(new Error('offline'))))
    );
    return;
  }

  // Navigation: serve shell
  if (request.mode === 'navigate') {
    e.respondWith(caches.match('/index.html').then((r) => r || fetch(request)));
    return;
  }

  // Static assets: cache-first
  e.respondWith(caches.match(request).then((r) => r || fetch(request)));
});
