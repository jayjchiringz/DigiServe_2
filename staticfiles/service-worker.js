const CACHE_NAME = 'digiserve-cache-v1';
const urlsToCache = [
    '/',
	'/static/offline.html',
    '/static/css/style_2.css',
	'/static/css/style.css',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
];

const OFFLINE_URL = '/static/offline.html';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll([...urlsToCache, OFFLINE_URL]);
        })
    );
});

// Fetch Event: Serve from Cache or Fetch from Network
self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request).then((response) => {
            return (
                response ||
                fetch(event.request).then((fetchResponse) => {
                    // Cache dynamic API responses
                    return caches.open(CACHE_NAME).then((cache) => {
                        if (event.request.url.startsWith('http')) {
                            cache.put(event.request, fetchResponse.clone());
                        }
                        return fetchResponse;
                    });
                }).catch(() => {
                    // Handle offline API requests (if needed)
                    if (event.request.mode === 'navigate') {
                        return caches.match('/offline.html');
					}
                })
            );
        })
    );
});

// Activate Event: Clear old caches
self.addEventListener('activate', (event) => {
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (!cacheWhitelist.includes(cacheName)) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});
