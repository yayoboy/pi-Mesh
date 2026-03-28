// Service Worker — network-first for static assets
const CACHE = 'pi-mesh-v3'
const STATIC = [
  '/static/style.css',
  '/static/app.js',
  '/static/map.js',
  '/static/chart.min.js',
]

self.addEventListener('install', e => {
  self.skipWaiting()
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return
  const url = new URL(e.request.url)
  // Strip query params for matching
  if (!STATIC.includes(url.pathname)) return
  // Network-first: try fresh copy, fall back to cache
  e.respondWith(
    fetch(e.request).then(response => {
      const clone = response.clone()
      caches.open(CACHE).then(c => c.put(e.request, clone))
      return response
    }).catch(() => caches.match(e.request))
  )
})
