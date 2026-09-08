/* Service worker — app-shell caching zodat de PWA ook offline werkt.
   Belangrijk: bij het aanpassen van style.css/app.js de CACHE-versie bumpen. */
const CACHE = "vitalytics-md3-v86";
const VERSION = "56";
const SHELL = ["/", "/static/style.css?v=" + VERSION, "/static/app.js?v=" + VERSION,
               "/manifest.webmanifest", "/static/icons/icon-192.png", "/favicon.ico"];

/* Deze bestanden altijd vers ophalen zodra de server bereikbaar is;
   de cache dient alleen als offline-fallback. Voorkomt verouderde UI. */
const NETWORK_FIRST = ["/static/style.css", "/static/app.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin !== location.origin) {
    // Google Fonts cachen zodat het lettertype ook offline beschikbaar is
    if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
      event.respondWith((async () => {
        const cache = await caches.open(CACHE + "-fonts");
        const cached = await cache.match(req);
        const fresh = fetch(req)
          .then((res) => {
            if (res && (res.ok || res.type === "opaque")) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || fresh;
      })());
    }
    return;
  }

  if (url.pathname.startsWith("/api/")) return; // nooit live-data cachen

  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        const cache = await caches.open(CACHE);
        cache.put(req, res.clone());
        return res;
      } catch (e) {
        return (await caches.match(req)) || (await caches.match("/"));
      }
    })());
    return;
  }

  // kritieke shell-bestanden: netwerk-eerst, cache als offline-fallback
  if (NETWORK_FIRST.some((p) => url.pathname.startsWith(p))) {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE);
      try {
        const res = await fetch(req);
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      } catch (e) {
        return (await cache.match(req)) || Response.error();
      }
    })());
    return;
  }

  // overige bestanden (iconen, uploads): cache-eerst met achtergrondverversing
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    const fresh = fetch(req)
      .then((res) => {
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      })
      .catch(() => cached);
    return cached || fresh;
  })());
});