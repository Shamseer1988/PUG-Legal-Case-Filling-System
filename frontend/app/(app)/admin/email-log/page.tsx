'use client';

import { Eye, RefreshCw, Send, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, API_BASE, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

type LogItem = {
  id: number;
  to_emails: string;
  subject: string;
  status: string;
  attempts: number;
  event: string;
  sent_at: string | null;
  created_at: string;
  error: string;
};

const STATUSES = ['', 'Queued', 'Sent', 'Failed', 'Bounced'];

const STATUS_CLS: Record<string, string> = {
  Sent: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40',
  Queued: 'bg-pug-gold-500/15 text-pug-gold-700 dark:text-pug-gold-300 border-pug-gold-500/40',
  Failed: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40',
  Bounced: 'bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/40',
};

export default function EmailLogPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [rows, setRows] = useState<LogItem[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string>('');

  async function load() {
    setLoading(true);
    try {
      const q = filter ? `?only=${encodeURIComponent(filter)}` : '';
      setRows(await api<LogItem[]>(`/api/v1/admin/email-log${q}`));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [filter]);

  async function openPreview(id: number) {
    setPreviewId(id);
    setPreviewHtml('Loading...');
    try {
      const r = await fetch(`${API_BASE}/api/v1/admin/email-log/${id}/preview`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      setPreviewHtml(await r.text());
    } catch {
      setPreviewHtml('<div style="padding:24px;color:#b3261e">Failed to load preview.</div>');
    }
  }

  async function resend(id: number) {
    try {
      await api(`/api/v1/admin/email-log/${id}/resend`, { method: 'POST' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Email Log</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Every outbound email recorded with rendered HTML, resend and bounce support.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            Status:
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s || 'All'}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={load}
            className="flex items-center gap-1 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <table className="w-full text-sm">
          <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <tr>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">To</th>
              <th className="px-4 py-3">Subject</th>
              <th className="px-4 py-3">Event</th>
              <th className="px-4 py-3">Attempts</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  Loading...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-[rgb(var(--color-muted))]">
                  No emails recorded.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2">
                    <span
                      className={
                        'inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
                        (STATUS_CLS[r.status] ?? 'bg-slate-500/10 text-slate-700 border-slate-500/40')
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {new Date(r.sent_at ?? r.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-xs">{r.to_emails}</td>
                  <td className="px-4 py-2">{r.subject}</td>
                  <td className="px-4 py-2 font-mono text-[11px]">{r.event || '-'}</td>
                  <td className="px-4 py-2 tabular-nums">{r.attempts}</td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => openPreview(r.id)}
                      className="mr-1 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <Eye className="h-3 w-3" /> Preview
                    </button>
                    <button
                      onClick={() => resend(r.id)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <Send className="h-3 w-3" /> Resend
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {previewId !== null && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-xl">
            <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-4 py-2">
              <div className="text-sm font-semibold">Email Preview &middot; #{previewId}</div>
              <button
                onClick={() => setPreviewId(null)}
                className="rounded p-1 hover:bg-[rgb(var(--color-border))]/40"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <iframe title="email" srcDoc={previewHtml} className="h-[70vh] w-full bg-white" />
          </div>
        </div>
      )}
    </div>
  );
}
