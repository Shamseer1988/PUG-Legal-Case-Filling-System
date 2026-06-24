/* eslint-disable */
/**
 * PUG Legal — Service Worker (Phase 32).
 *
 * Two jobs:
 *   1. Provide a small "shell" cache so the app keeps rendering when
 *      the user is offline (login/landing/icons). This is intentionally
 *      conservative — case data is never cached, only the static shell.
 *   2. Receive Web Push events and surface them as system
 *      notifications that deep-link back to the originating case.
 */

const CACHE = 'pug-legal-shell-v1';
const SHELL = [
  '/',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => undefined)),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Never cache API traffic — case data is sensitive and must stay
  // request-fresh. Only the static shell is offline-friendly.
  if (url.pathname.startsWith('/api/')) return;
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(req).then(
      (cached) =>
        cached ||
        fetch(req)
          .then((resp) => {
            if (resp && resp.status === 200 && resp.type === 'basic') {
              const clone = resp.clone();
              caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => undefined);
            }
            return resp;
          })
          .catch(() => cached),
    ),
  );
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: 'PUG Legal', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'PUG Legal';
  const body = data.body || '';
  const url = data.url || '/';
  const tag = data.event ? `pug-${data.event}-${data.case_id || ''}` : undefined;

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag,
      renotify: true,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      data: { url },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  const target = (event.notification && event.notification.data && event.notification.data.url) || '/';
  event.notification.close();
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const c of clients) {
          if ('focus' in c) {
            try {
              c.navigate(target);
              return c.focus();
            } catch {
              // navigate may be blocked across origins; fall through
            }
          }
        }
        if (self.clients.openWindow) return self.clients.openWindow(target);
        return undefined;
      }),
  );
});
