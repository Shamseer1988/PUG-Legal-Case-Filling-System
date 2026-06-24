'use client';

import Link from 'next/link';
import { Play, Pause, Plus, Trash2, Clock, AlertTriangle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Schedule = {
  id: number;
  name: string;
  report_key: string;
  cron: string;
  recipients: string[];
  formats: string[];
  is_active: boolean;
  last_run_at: string | null;
  last_run_status: string;
  last_run_error: string;
  next_run_at: string | null;
};

export default function SchedulesListPage() {
  const [rows, setRows] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setRows(await api<Schedule[]>('/api/v1/scheduled-reports'));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function toggle(s: Schedule) {
    try {
      await api(`/api/v1/scheduled-reports/${s.id}/${s.is_active ? 'pause' : 'resume'}`, {
        method: 'POST',
      });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function runNow(s: Schedule) {
    try {
      await api(`/api/v1/scheduled-reports/${s.id}/run-now`, { method: 'POST' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function remove(s: Schedule) {
    if (!confirm(`Delete schedule "${s.name}"?`)) return;
    try {
      await api(`/api/v1/scheduled-reports/${s.id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Scheduled Reports</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Cron-based reports emailed with branded summary + PDF / Excel attachments.
          </p>
        </div>
        <Link
          href="/schedules/new"
          className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
        >
          <Plus className="h-4 w-4" /> New Schedule
        </Link>
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
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Report</th>
              <th className="px-4 py-3">Cron</th>
              <th className="px-4 py-3">Recipients</th>
              <th className="px-4 py-3">Next Run</th>
              <th className="px-4 py-3">Last Run</th>
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
                  No schedules yet. Click <strong>New Schedule</strong> to create one.
                </td>
              </tr>
            ) : (
              rows.map((s) => (
                <tr key={s.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2">
                    <Link href={`/schedules/${s.id}`} className="font-semibold hover:underline">
                      {s.name}
                    </Link>
                    <div className="text-[10px] text-[rgb(var(--color-muted))]">
                      {s.is_active ? (
                        <span className="text-emerald-700 dark:text-emerald-300">Active</span>
                      ) : (
                        <span>Paused</span>
                      )}
                      {' '}&middot; {s.formats.join(', ').toUpperCase() || 'PDF'}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs">{s.report_key}</td>
                  <td className="px-4 py-2 font-mono text-xs">{s.cron}</td>
                  <td className="px-4 py-2 text-xs">
                    {s.recipients.slice(0, 2).join(', ') || '-'}
                    {s.recipients.length > 2 && ` +${s.recipients.length - 2}`}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {s.next_run_at ? (
                      <span className="inline-flex items-center gap-1 text-[rgb(var(--color-muted))]">
                        <Clock className="h-3 w-3" />
                        {new Date(s.next_run_at).toLocaleString()}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {s.last_run_at ? (
                      <span
                        className={
                          s.last_run_status === 'Success'
                            ? 'text-emerald-700 dark:text-emerald-300'
                            : 'inline-flex items-center gap-1 text-rose-700 dark:text-rose-300'
                        }
                      >
                        {s.last_run_status === 'Failed' && (
                          <AlertTriangle className="h-3 w-3" />
                        )}
                        {s.last_run_status} - {new Date(s.last_run_at).toLocaleString()}
                      </span>
                    ) : (
                      <span className="text-[rgb(var(--color-muted))]">Never</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => runNow(s)}
                      className="mr-1 inline-flex items-center gap-1 rounded bg-pug-gold-500 px-2 py-1 text-[11px] font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
                    >
                      <Play className="h-3 w-3" /> Run
                    </button>
                    <button
                      onClick={() => toggle(s)}
                      className="mr-1 inline-flex items-center gap-1 rounded border border-[rgb(var(--color-border))] px-2 py-1 text-[11px] font-semibold hover:bg-[rgb(var(--color-border))]/40"
                    >
                      {s.is_active ? (
                        <>
                          <Pause className="h-3 w-3" /> Pause
                        </>
                      ) : (
                        <>
                          <Play className="h-3 w-3" /> Resume
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => remove(s)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-rose-600 hover:bg-rose-500/10"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
