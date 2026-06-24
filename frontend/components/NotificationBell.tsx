'use client';

import { Bell, Check, CheckCheck, Wifi, WifiOff } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import {
  openNotificationStream,
  type SseNotification,
} from '@/lib/notificationStream';

type Note = SseNotification;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  // 'sse' = real-time stream is healthy, 'poll' = fell back to 30s
  // polling because SSE failed (proxy stripping the stream, network
  // hiccup that exhausted reconnects). The icon next to the bell
  // surfaces this so an operator can spot a degraded environment.
  const [mode, setMode] = useState<'sse' | 'poll'>('sse');
  const ref = useRef<HTMLDivElement>(null);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadCount = useCallback(async () => {
    try {
      const r = await api<{ unread: number }>('/api/v1/notifications/unread-count');
      setUnread(r.unread);
    } catch {
      /* ignore */
    }
  }, []);

  async function loadItems() {
    try {
      setItems(await api<Note[]>('/api/v1/notifications?limit=30'));
    } catch {
      /* ignore */
    }
  }

  // Open SSE on mount; on fatal failure, fall back to 30s polling
  // so the bell still works behind a proxy that drops text/event-stream.
  useEffect(() => {
    let stream = openNotificationStream({
      onHello: ({ unread }) => setUnread(unread),
      onUnread: ({ unread }) => setUnread(unread),
      onNotification: (note) => {
        setUnread((u) => u + (note.is_read ? 0 : 1));
        // Prepend to the dropdown list (cap at 50 in memory)
        setItems((arr) => [note, ...arr.filter((x) => x.id !== note.id)].slice(0, 50));
      },
      onFatal: () => {
        setMode('poll');
        loadCount();
        pollTimer.current = setInterval(loadCount, 30_000);
      },
    });

    // Belt-and-braces: load count once on mount in case the SSE
    // ticket takes a moment to issue or the user opens the bell
    // before the hello event lands.
    loadCount();

    return () => {
      stream.close();
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, [loadCount]);

  useEffect(() => {
    if (open) loadItems();
  }, [open]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, []);

  async function markOne(n: Note) {
    await api(`/api/v1/notifications/${n.id}/read`, { method: 'POST' });
    setItems((arr) => arr.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
    setUnread((u) => Math.max(0, u - 1));
  }

  async function markAll() {
    await api('/api/v1/notifications/read-all', { method: 'POST' });
    setItems((arr) => arr.map((x) => ({ ...x, is_read: true })));
    setUnread(0);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        className="relative flex h-9 w-9 items-center justify-center rounded-full border border-[rgb(var(--color-border))] hover:bg-[rgb(var(--color-border))]/40"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-30 w-[24rem] max-w-[90vw] rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-xl">
          <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-3 py-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              Notifications
              <span
                title={
                  mode === 'sse'
                    ? 'Real-time stream connected'
                    : 'Fell back to 30s polling (SSE unavailable)'
                }
                className={
                  'inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ' +
                  (mode === 'sse'
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                    : 'bg-amber-500/15 text-amber-700 dark:text-amber-300')
                }
              >
                {mode === 'sse' ? (
                  <>
                    <Wifi className="h-2.5 w-2.5" /> Live
                  </>
                ) : (
                  <>
                    <WifiOff className="h-2.5 w-2.5" /> Polling
                  </>
                )}
              </span>
            </div>
            {unread > 0 && (
              <button
                onClick={markAll}
                className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-semibold text-pug-gold-700 hover:bg-pug-gold-500/10 dark:text-pug-gold-300"
              >
                <CheckCheck className="h-3 w-3" /> Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[26rem] overflow-y-auto">
            {items.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-[rgb(var(--color-muted))]">
                Nothing here yet.
              </div>
            ) : (
              <ul className="divide-y divide-[rgb(var(--color-border))]">
                {items.map((n) => (
                  <li
                    key={n.id}
                    className={
                      'group px-3 py-2 hover:bg-[rgb(var(--color-border))]/30 ' +
                      (n.is_read ? '' : 'bg-pug-gold-500/5')
                    }
                  >
                    <div className="flex items-start gap-2">
                      <div
                        className={
                          'mt-1 h-2 w-2 shrink-0 rounded-full ' +
                          (n.is_read ? 'bg-transparent' : 'bg-pug-gold-500')
                        }
                      />
                      <div className="min-w-0 flex-1">
                        <Link
                          href={n.link || '#'}
                          onClick={() => markOne(n)}
                          className="block"
                        >
                          <div className="truncate text-sm font-semibold">{n.title}</div>
                          {n.body && (
                            <div className="line-clamp-2 text-xs text-[rgb(var(--color-muted))]">
                              {n.body}
                            </div>
                          )}
                          <div className="mt-0.5 text-[10px] text-[rgb(var(--color-muted))]">
                            {new Date(n.created_at).toLocaleString()}
                          </div>
                        </Link>
                      </div>
                      {!n.is_read && (
                        <button
                          onClick={() => markOne(n)}
                          title="Mark read"
                          className="rounded p-1 text-[rgb(var(--color-muted))] opacity-0 hover:bg-[rgb(var(--color-border))]/30 group-hover:opacity-100"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
