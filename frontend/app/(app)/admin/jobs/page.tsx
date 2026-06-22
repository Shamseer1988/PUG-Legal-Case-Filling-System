'use client';

import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  PlayCircle,
  RefreshCw,
  Timer,
} from 'lucide-react';
import { Fragment, useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type JobRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  ok: boolean;
  detail: string;
};

type JobSummary = {
  job_id: string;
  interval_seconds: number | null;
  next_run_at: string | null;
  running: boolean;
  last_run: JobRun | null;
  last_ok: boolean | null;
  success_rate_recent: number | null;
};

const PRETTY: Record<string, string> = {
  'scheduled-reports-tick': 'Scheduled Reports',
  'email-queue-tick': 'Email Queue',
  'sla-breach-tick': 'SLA Breach Scanner',
  'hearing-reminder-tick': 'Hearing Reminders',
};

function prettyName(id: string): string {
  return PRETTY[id] ?? id;
}

function fmtInterval(secs: number | null): string {
  if (!secs) return '—';
  if (secs % 60 === 0) return `${secs / 60} min`;
  return `${secs}s`;
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString();
}

export default function JobMonitorPage() {
  const [rows, setRows] = useState<JobSummary[]>([]);
  const [history, setHistory] = useState<Record<string, JobRun[]>>({});
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    setErr(null);
    setLoading(true);
    try {
      setRows(await api<JobSummary[]>('/api/v1/admin/jobs'));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = window.setInterval(load, 15_000);
    return () => window.clearInterval(t);
  }, []);

  async function toggleHistory(jobId: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
    if (!history[jobId]) {
      try {
        const data = await api<JobRun[]>(
          `/api/v1/admin/jobs/${encodeURIComponent(jobId)}/history?limit=50`,
        );
        setHistory((prev) => ({ ...prev, [jobId]: data }));
      } catch (e) {
        setErr((e as ApiError).message);
      }
    }
  }

  async function runNow(jobId: string) {
    setBusy(jobId);
    setErr(null);
    setInfo(null);
    try {
      await api(`/api/v1/admin/jobs/${encodeURIComponent(jobId)}/run-now`, {
        method: 'POST',
      });
      setInfo(`Triggered ${prettyName(jobId)}.`);
      // Give APScheduler a beat to actually fire before refreshing.
      window.setTimeout(load, 1500);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Job Monitor</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Background scheduler ticks. Auto-refreshes every 15 seconds.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
          {info}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <table className="w-full text-sm">
          <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <tr>
              <th className="px-4 py-2 w-8"></th>
              <th className="px-4 py-2">Job</th>
              <th className="px-4 py-2 w-24">Interval</th>
              <th className="px-4 py-2 w-28">Last Run</th>
              <th className="px-4 py-2 w-28">Next Run</th>
              <th className="px-4 py-2 w-24">Last Status</th>
              <th className="px-4 py-2 w-24">Success</th>
              <th className="px-4 py-2 w-32"></th>
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-xs text-[rgb(var(--color-muted))]">
                  Loading…
                </td>
              </tr>
            )}
            {rows.map((j) => (
              <Fragment key={j.job_id}>
                <tr className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-2 py-2">
                    <button
                      type="button"
                      onClick={() => toggleHistory(j.job_id)}
                      className="text-[rgb(var(--color-muted))] hover:text-[rgb(var(--color-fg))]"
                      title="Toggle history"
                    >
                      {open.has(j.job_id) ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-2">
                    <div className="font-semibold">{prettyName(j.job_id)}</div>
                    <code className="text-[10px] text-[rgb(var(--color-muted))]">{j.job_id}</code>
                  </td>
                  <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                    <Timer className="-mt-0.5 mr-1 inline h-3 w-3" />
                    {fmtInterval(j.interval_seconds)}
                  </td>
                  <td className="px-4 py-2 text-xs">{fmtTime(j.last_run?.started_at ?? null)}</td>
                  <td className="px-4 py-2 text-xs">
                    {j.running ? fmtTime(j.next_run_at) : (
                      <span className="text-rose-600 dark:text-rose-300">scheduler down</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {j.last_ok === null && (
                      <span className="text-xs text-[rgb(var(--color-muted))]">—</span>
                    )}
                    {j.last_ok === true && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                        <CheckCircle2 className="h-3 w-3" /> OK
                      </span>
                    )}
                    {j.last_ok === false && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-300">
                        <AlertTriangle className="h-3 w-3" /> Failed
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {j.success_rate_recent === null
                      ? '—'
                      : `${Math.round(j.success_rate_recent * 100)}%`}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => runNow(j.job_id)}
                      disabled={busy === j.job_id || !j.running}
                      className="inline-flex items-center gap-1 rounded-md bg-pug-gold-500 px-2 py-1 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
                    >
                      <PlayCircle className="h-3.5 w-3.5" />
                      {busy === j.job_id ? 'Running…' : 'Run Now'}
                    </button>
                  </td>
                </tr>
                {open.has(j.job_id) && (
                  <tr className="border-t border-[rgb(var(--color-border))] bg-[rgb(var(--color-border))]/10">
                    <td></td>
                    <td colSpan={7} className="px-4 py-3">
                      <div className="text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                        Recent runs
                      </div>
                      {!history[j.job_id] && (
                        <div className="py-2 text-xs text-[rgb(var(--color-muted))]">Loading…</div>
                      )}
                      {history[j.job_id] && history[j.job_id].length === 0 && (
                        <div className="py-2 text-xs text-[rgb(var(--color-muted))]">
                          No runs recorded yet.
                        </div>
                      )}
                      {history[j.job_id] && history[j.job_id].length > 0 && (
                        <table className="mt-2 w-full text-xs">
                          <thead className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                            <tr>
                              <th className="py-1 text-left">Started</th>
                              <th className="py-1 text-left">Duration</th>
                              <th className="py-1 text-left">OK</th>
                              <th className="py-1 text-left">Detail</th>
                            </tr>
                          </thead>
                          <tbody>
                            {history[j.job_id].map((r) => (
                              <tr key={r.id} className="border-t border-[rgb(var(--color-border))]/50">
                                <td className="py-1">{fmtTime(r.started_at)}</td>
                                <td className="py-1">{r.duration_ms} ms</td>
                                <td className="py-1">
                                  {r.ok ? (
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                                  ) : (
                                    <AlertTriangle className="h-3.5 w-3.5 text-rose-600" />
                                  )}
                                </td>
                                <td className="py-1 font-mono text-[10px] text-[rgb(var(--color-muted))]">
                                  {r.detail || '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
