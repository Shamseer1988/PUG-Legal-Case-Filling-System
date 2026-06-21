'use client';

import { api, API_BASE } from './api';

export type SseNotification = {
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

type StreamHandlers = {
  onHello?: (payload: { unread: number; last_id: number }) => void;
  onNotification?: (note: SseNotification) => void;
  onUnread?: (payload: { unread: number }) => void;
  /** Called when the SSE socket goes down for good (after retries
   *  exhaust). Caller should fall back to polling. */
  onFatal?: () => void;
};

type Closer = { close: () => void };

const TICKET_PATH = '/api/v1/auth/stream-ticket';
const STREAM_PATH = '/api/v1/notifications/stream';
const MAX_RECONNECTS = 4;
const RECONNECT_DELAYS_MS = [1_000, 3_000, 10_000, 30_000];

/** Opens an authenticated SSE stream to /notifications/stream.
 *
 *  Implements:
 *  - short-lived stream ticket fetched from /auth/stream-ticket
 *  - auto-reconnect with exponential backoff
 *  - hard fallback after MAX_RECONNECTS failures (caller's onFatal()
 *    can swap to plain polling so the bell still works behind a
 *    proxy that strips text/event-stream).
 */
export function openNotificationStream(handlers: StreamHandlers): Closer {
  let es: EventSource | null = null;
  let reconnectAttempt = 0;
  let cancelled = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  async function connect() {
    if (cancelled) return;
    let ticket: string;
    try {
      const r = await api<{ ticket: string }>(TICKET_PATH, { method: 'POST' });
      ticket = r.ticket;
    } catch {
      scheduleReconnect();
      return;
    }
    if (cancelled) return;
    const url = `${API_BASE}${STREAM_PATH}?ticket=${encodeURIComponent(ticket)}`;
    es = new EventSource(url);

    es.addEventListener('hello', (e) => {
      try {
        handlers.onHello?.(JSON.parse((e as MessageEvent).data));
      } catch {
        /* ignore */
      }
      // First successful frame -> reset backoff
      reconnectAttempt = 0;
    });
    es.addEventListener('notification', (e) => {
      try {
        handlers.onNotification?.(JSON.parse((e as MessageEvent).data));
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('unread', (e) => {
      try {
        handlers.onUnread?.(JSON.parse((e as MessageEvent).data));
      } catch {
        /* ignore */
      }
    });
    es.addEventListener('bye', () => {
      // Server told us to close (max-lifetime). Reconnect immediately
      // with a fresh ticket - don't count this against the backoff.
      teardown();
      reconnectAttempt = 0;
      if (!cancelled) connect();
    });
    es.onerror = () => {
      // EventSource auto-retries internally but with a 3s default;
      // we close + manage the schedule ourselves so we can give up
      // and fall back to polling after enough failures.
      teardown();
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (cancelled) return;
    if (reconnectAttempt >= MAX_RECONNECTS) {
      handlers.onFatal?.();
      return;
    }
    const delay = RECONNECT_DELAYS_MS[reconnectAttempt] ?? 30_000;
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(connect, delay);
  }

  function teardown() {
    try {
      es?.close();
    } catch {
      /* ignore */
    }
    es = null;
  }

  connect();

  return {
    close() {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      teardown();
    },
  };
}
