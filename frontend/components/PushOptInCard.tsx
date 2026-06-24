'use client';

import { Bell, BellOff, CheckCircle2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  checkPushSupport,
  currentSubscription,
  subscribeToPush,
  unsubscribeFromPush,
} from '@/lib/push';

type Status = 'unknown' | 'unsupported' | 'denied' | 'off' | 'on';

export function PushOptInCard() {
  const [status, setStatus] = useState<Status>('unknown');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const support = checkPushSupport();
      if (!support.supported) {
        if (!cancelled) setStatus('unsupported');
        return;
      }
      if (typeof Notification !== 'undefined' && Notification.permission === 'denied') {
        if (!cancelled) setStatus('denied');
        return;
      }
      const sub = await currentSubscription();
      if (!cancelled) setStatus(sub ? 'on' : 'off');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function enable() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      await subscribeToPush();
      setStatus('on');
      setInfo('Push notifications enabled on this device.');
    } catch (ex) {
      setErr((ex as Error).message || 'Could not enable push notifications.');
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      await unsubscribeFromPush();
      setStatus('off');
      setInfo('Push notifications disabled on this device.');
    } catch (ex) {
      setErr((ex as Error).message || 'Could not disable push notifications.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          <Bell className="h-4 w-4" /> Push Notifications
        </h2>
        {status === 'on' && (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Active
          </span>
        )}
        {status === 'off' && (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
            <BellOff className="h-3 w-3" /> Off
          </span>
        )}
      </div>

      <p className="mb-3 text-xs text-[rgb(var(--color-muted))]">
        Get a system-level notification on this device when a case is
        assigned to you, approved, rejected, or filed in court — even
        when the app tab is closed. You can enable this per device.
      </p>

      {err && (
        <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="mb-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
          {info}
        </div>
      )}

      {status === 'unsupported' && (
        <p className="text-xs text-[rgb(var(--color-muted))]">
          This browser does not support Web Push notifications. Try
          Chrome, Edge, Firefox, or installing PUG Legal as an app on iOS 16.4+.
        </p>
      )}
      {status === 'denied' && (
        <p className="text-xs text-rose-600 dark:text-rose-300">
          Notifications are blocked in your browser settings. Allow
          notifications for this site, then reload the page.
        </p>
      )}
      {status === 'off' && (
        <button
          onClick={enable}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
        >
          <Bell className="h-4 w-4" />
          {busy ? 'Enabling...' : 'Enable on this device'}
        </button>
      )}
      {status === 'on' && (
        <button
          onClick={disable}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-md border border-rose-500/40 px-3 py-2 text-sm text-rose-600 hover:bg-rose-500/10 disabled:opacity-50"
        >
          <BellOff className="h-4 w-4" />
          {busy ? 'Disabling...' : 'Disable on this device'}
        </button>
      )}
    </section>
  );
}
