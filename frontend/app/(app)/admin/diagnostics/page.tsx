'use client';

import { Activity, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Check = { name: string; ok: boolean; detail: string };
type DiagnosticsBody = {
  app: { version: string; checked_at: string };
  checks: Check[];
};

export default function DiagnosticsPage() {
  const [data, setData] = useState<DiagnosticsBody | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setErr(null);
    try {
      setData(await api<DiagnosticsBody>('/api/v1/diagnostics'));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Health &amp; Diagnostics</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Live status of every subsystem the app depends on.
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

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                App Version
              </div>
              <div className="mt-1 text-lg font-bold">{data.app.version}</div>
            </div>
            <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Checks
              </div>
              <div className="mt-1 text-lg font-bold">{data.checks.length}</div>
            </div>
            <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Passing
              </div>
              <div className="mt-1 text-lg font-bold text-emerald-600">
                {data.checks.filter((c) => c.ok).length}
              </div>
            </div>
            <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Failing
              </div>
              <div className="mt-1 text-lg font-bold text-rose-600">
                {data.checks.filter((c) => !c.ok).length}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
            <table className="w-full text-sm">
              <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
                <tr>
                  <th className="px-4 py-2 w-20">Status</th>
                  <th className="px-4 py-2">Component</th>
                  <th className="px-4 py-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.checks.map((c) => (
                  <tr key={c.name} className="border-t border-[rgb(var(--color-border))]">
                    <td className="px-4 py-2">
                      {c.ok ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
                          <CheckCircle2 className="h-3 w-3" /> OK
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-300">
                          <AlertTriangle className="h-3 w-3" /> Fail
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 font-semibold">{c.name}</td>
                    <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                      {c.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-[rgb(var(--color-border))] px-4 py-2 text-[10px] text-[rgb(var(--color-muted))]">
              <Activity className="-mt-0.5 mr-1 inline h-3 w-3" />
              Checked at {new Date(data.app.checked_at).toLocaleString()}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
