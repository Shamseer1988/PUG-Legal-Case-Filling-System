'use client';

import { api } from './api';

/** Phase 32 helpers for managing the user's Web Push subscription. */

export type PushSupport = {
  supported: boolean;
  reason?: string;
};

export function checkPushSupport(): PushSupport {
  if (typeof window === 'undefined') return { supported: false, reason: 'ssr' };
  if (!('serviceWorker' in navigator)) return { supported: false, reason: 'no-sw' };
  if (!('PushManager' in window)) return { supported: false, reason: 'no-push' };
  if (!('Notification' in window)) return { supported: false, reason: 'no-notif' };
  return { supported: true };
}

/** Convert base64url (no padding) into the Uint8Array the
 *  PushManager.subscribe applicationServerKey expects. */
function urlBase64ToUint8Array(b64: string): Uint8Array {
  const padding = '='.repeat((4 - (b64.length % 4)) % 4);
  const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function getReadyRegistration(): Promise<ServiceWorkerRegistration> {
  const reg = await navigator.serviceWorker.getRegistration('/');
  if (reg) return reg;
  return navigator.serviceWorker.register('/sw.js', { scope: '/' });
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  if (!checkPushSupport().supported) return null;
  const reg = await navigator.serviceWorker.getRegistration('/');
  if (!reg) return null;
  return (await reg.pushManager.getSubscription()) ?? null;
}

export async function subscribeToPush(): Promise<PushSubscription> {
  const support = checkPushSupport();
  if (!support.supported) {
    throw new Error('Push notifications are not supported by this browser.');
  }
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') {
    throw new Error('Notification permission was not granted.');
  }
  const { public_key } = await api<{ public_key: string }>(
    '/api/v1/push/vapid-public-key',
  );
  const reg = await getReadyRegistration();
  const existing = await reg.pushManager.getSubscription();
  const sub =
    existing ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    }));
  const raw = sub.toJSON() as { keys?: { p256dh?: string; auth?: string } };
  const p256dh = raw.keys?.p256dh ?? '';
  const auth = raw.keys?.auth ?? '';
  await api('/api/v1/push/subscribe', {
    method: 'POST',
    body: {
      endpoint: sub.endpoint,
      p256dh,
      auth,
      user_agent: navigator.userAgent.slice(0, 480),
    },
  });
  return sub;
}

export async function unsubscribeFromPush(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  try {
    await api('/api/v1/push/unsubscribe', {
      method: 'POST',
      body: { endpoint: sub.endpoint },
    });
  } catch {
    /* ignore — best effort */
  }
  try {
    await sub.unsubscribe();
  } catch {
    /* ignore */
  }
}
