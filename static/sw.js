// Service Worker — cache static assets only
const CACHE = 'pi-mesh-v1'
const STATIC = [
  '/static/style.css',
  '/static/app.js',
  '/static/chart.min.js',
]

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', e => {
  // Only cache GET requests for static assets
  if (e.request.method !== 'GET') return
  const url = new URL(e.request.url)
  if (!STATIC.includes(url.pathname)) return
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  )
})
