/* Plantation field app service worker. __VERSION__ and __ASSETS__ are filled in by the server,
   so a new release changes this file and the phone fetches the new files. */
const VERSION = '__VERSION__';
const ASSETS = __ASSETS__;
const APP_PATH = '/plantation/field';
const CACHE = 'ss-field-' + VERSION;
const NAV_TIMEOUT_MS = 3000;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ASSETS.map((u) => new Request(u, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('ss-field-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function timeout(ms) {
  return new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms));
}

async function shell(request) {
  const cache = await caches.open(CACHE);
  try {
    // Network first so releases arrive, but never make a phone with bad signal wait long.
    const response = await Promise.race([fetch(request), timeout(NAV_TIMEOUT_MS)]);
    if (response.ok) cache.put(APP_PATH, response.clone());
    return response;
  } catch (e) {
    const cached = await cache.match(APP_PATH, { ignoreSearch: true });
    return cached || new Response('Offline', { status: 503 });
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith(APP_PATH + '/api/')) return; // data calls: the app handles failures
  if (url.pathname === APP_PATH) {
    event.respondWith(shell(request));
    return;
  }
  if (ASSETS.includes(url.pathname)) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => (await cache.match(url.pathname)) || fetch(request))
    );
  }
});
