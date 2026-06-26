'use client';

import { useAuthStore } from './auth';

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  status: number;
  payload?: unknown;
  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

/** Wipe the auth store and bounce the browser to /login. Safe to call
 *  multiple times (the early-return short-circuits repeat redirects). */
function forceLogin(): void {
  try {
    useAuthStore.getState().clear();
  } catch {
    /* zustand teardown - ignore */
  }
  if (typeof window === 'undefined') return;
  const cur = window.location.pathname;
  if (cur === '/login' || cur.startsWith('/login')) return;
  const next = encodeURIComponent(cur + window.location.search);
  window.location.replace(`/login?next=${next}`);
}

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens } = useAuthStore.getState();
  if (!refreshToken) return null;
  try {
    const r = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!r.ok) return null;
    const data = await r.json();
    setTokens(data.access_token, data.refresh_token);
    return data.access_token as string;
  } catch {
    return null;
  }
}

type Options = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  auth?: boolean;
};

/** Low-level authenticated fetch that handles the 401 -> refresh ->
 *  retry -> forceLogin flow once. Use this for endpoints that return
 *  blobs or accept multipart bodies (the json `api()` helper above
 *  is the right choice for everything else).
 *
 *  The caller supplies the full RequestInit so it can set FormData,
 *  custom Accept headers, etc. We layer the Authorization header on
 *  top and never set Content-Type (browsers must set it for multipart
 *  uploads).
 */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
  opts: { auth?: boolean } = {},
): Promise<Response> {
  const { auth = true } = opts;
  const withAuth = (token: string | null): RequestInit => {
    const h = new Headers(init.headers || {});
    if (token) h.set('Authorization', `Bearer ${token}`);
    return { ...init, headers: h, cache: 'no-store' };
  };

  const initialToken = auth ? useAuthStore.getState().accessToken ?? null : null;
  let res = await fetch(`${API_BASE}${path}`, withAuth(initialToken));

  if (res.status === 401 && auth) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await fetch(`${API_BASE}${path}`, withAuth(newToken));
      if (res.status === 401) {
        forceLogin();
        throw new ApiError(401, 'Session expired. Please sign in again.');
      }
    } else {
      forceLogin();
      throw new ApiError(401, 'Session expired. Please sign in again.');
    }
  }
  return res;
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, auth = true } = opts;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const res = await apiFetch(
    path,
    {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    },
    { auth },
  );

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const data = text ? safeJson(text) : undefined;

  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(data, res.statusText), data);
  }
  return data as T;
}

/**
 * FastAPI returns 422 with `detail` as an array of {loc, msg, type} objects,
 * 4xx errors with `detail` as a string, and some endpoints return no body.
 * Normalise every case to a human-readable string.
 */
function extractDetail(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object' || !('detail' in data)) return fallback;
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        if (e && typeof e === 'object') {
          const obj = e as Record<string, unknown>;
          const msg = typeof obj.msg === 'string' ? obj.msg : '';
          const loc = Array.isArray(obj.loc) ? obj.loc.join('.') : '';
          return loc ? `${loc}: ${msg}` : msg || JSON.stringify(e);
        }
        return String(e);
      })
      .join('; ');
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return fallback;
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
