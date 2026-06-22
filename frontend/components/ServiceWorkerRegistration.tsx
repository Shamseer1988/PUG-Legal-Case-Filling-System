'use client';

import { useEffect } from 'react';

/**
 * Registers the Phase 32 service worker. Mounted once at the top
 * of the authenticated layout — the SW is what powers the install
 * prompt, the offline shell, and the Web Push event handler.
 *
 * Registration is best-effort: any failure (HTTP/insecure origin,
 * private window, browser without SW support) is silently ignored
 * so the app still works without push.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator)) return;
    const onLoad = () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {
        /* ignore */
      });
    };
    if (document.readyState === 'complete') onLoad();
    else window.addEventListener('load', onLoad, { once: true });
    return () => window.removeEventListener('load', onLoad);
  }, []);
  return null;
}
