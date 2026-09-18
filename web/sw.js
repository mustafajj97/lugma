// Lugma service worker: opens instantly and works offline.
// - App files: served from cache, refreshed in the background (stale-while-revalidate).
// - Offers data: always tries the network first so you see today's offers; falls back to the
//   last copy when offline. The page itself hides anything past its end date either way.
const CACHE = "lugma-v3";
const SHELL = ["./", "index.html", "app.js", "style.css", "manifest.webmanifest", "icon.svg", "icon-180.png", "icon-192.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;   // logos, fonts, links: straight to network

  if (url.pathname.endsWith("/data/offers.json")) {
    e.respondWith(
      fetch(e.request, { cache: "no-cache" })
        .then(res => { if (res.ok) caches.open(CACHE).then(c => c.put("data/offers.json", res.clone())); return res; })
        .catch(() => caches.match("data/offers.json"))
    );
    return;
  }

  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(hit => {
      const net = fetch(e.request)
        .then(res => { if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone())); return res; })
        .catch(() => hit);
      return hit || net;
    })
  );
});
