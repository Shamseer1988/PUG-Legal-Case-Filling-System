'use client';

import { Bell, Check, CheckCheck } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

type Note = {
  id: number;
  title: string;
  body: string;
  link: string;
  event: string;
  related_case_id: number | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
};

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Note[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    loadCount();
    const t = setInterval(loadCount, 30_000);
    return () => clearInterval(t);
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
    loadCount();
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
            <div className="text-sm font-semibold">Notifications</div>
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
