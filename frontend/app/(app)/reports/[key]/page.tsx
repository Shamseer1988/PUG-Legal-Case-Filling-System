'use client';

import { Download, FileSpreadsheet, FileText, Printer, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { api, API_BASE, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

type ParamDef = {
  name: string;
  type: string;
  label: string;
  options: string[] | null;
  required: boolean;
};

type ReportDescriptor = {
  key: string;
  name: string;
  description: string;
  params: ParamDef[];
};

type ReportColumn = { key: string; label: string; type: string };

type ReportData = {
  title: string;
  subtitle: string;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  params: Record<string, string>;
};

export default function ReportRunnerPage() {
  const params = useParams<{ key: string }>();
  const reportKey = params.key;
  const token = useAuthStore((s) => s.accessToken);

  const [descriptor, setDescriptor] = useState<ReportDescriptor | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [data, setData] = useState<ReportData | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await api<ReportDescriptor[]>('/api/v1/reports');
        const desc = all.find((r) => r.key === reportKey) || null;
        setDescriptor(desc);
      } catch (e) {
        setErr((e as ApiError).message);
      }
    })();
  }, [reportKey]);

  // Auto-run on first load
  useEffect(() => {
    if (descriptor) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [descriptor]);

  function up(name: string, value: string) {
    setParamValues((v) => ({ ...v, [name]: value }));
  }

  const qs = useMemo(() => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(paramValues)) {
      if (v !== '') u.set(k, v);
    }
    const s = u.toString();
    return s ? `?${s}` : '';
  }, [paramValues]);

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const d = await api<ReportData>(`/api/v1/reports/${reportKey}${qs}`);
      setData(d);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function download(format: 'xlsx' | 'pdf') {
    try {
      const r = await fetch(`${API_BASE}/api/v1/reports/${reportKey}.${format}${qs}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!r.ok) throw new Error(`Download failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${reportKey}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="space-y-4 print:space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <div>
          <Link
            href="/reports"
            className="text-xs text-pug-gold-700 hover:underline dark:text-pug-gold-400"
          >
            &larr; All reports
          </Link>
          <h1 className="text-xl font-semibold">{descriptor?.name ?? reportKey}</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">{descriptor?.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => download('xlsx')}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <FileSpreadsheet className="h-4 w-4" /> Excel
          </button>
          <button
            onClick={() => download('pdf')}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <FileText className="h-4 w-4" /> PDF
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <Printer className="h-4 w-4" /> Print
          </button>
        </div>
      </div>

      {descriptor && descriptor.params.length > 0 && (
        <div className="flex flex-wrap items-end gap-3 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft print:hidden">
          {descriptor.params.map((p) => (
            <label key={p.name} className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                {p.label}
              </span>
              {p.type === 'select' ? (
                <select
                  value={paramValues[p.name] ?? ''}
                  onChange={(e) => up(p.name, e.target.value)}
                  className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
                >
                  {(p.options ?? []).map((o) => (
                    <option key={o} value={o}>
                      {o || 'All'}
                    </option>
                  ))}
                </select>
              ) : p.type === 'date' ? (
                <input
                  type="date"
                  value={paramValues[p.name] ?? ''}
                  onChange={(e) => up(p.name, e.target.value)}
                  className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
                />
              ) : (
                <input
                  type="text"
                  value={paramValues[p.name] ?? ''}
                  onChange={(e) => up(p.name, e.target.value)}
                  className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
                />
              )}
            </label>
          ))}
          <button
            onClick={run}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
          >
            <RefreshCw className={'h-4 w-4 ' + (busy ? 'animate-spin' : '')} /> Run
          </button>
        </div>
      )}

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {data && (
        <div className="report-area rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
          <div className="border-b border-[rgb(var(--color-border))] px-4 py-3">
            <h2 className="text-lg font-semibold">{data.title}</h2>
            {data.subtitle && (
              <p className="text-xs text-[rgb(var(--color-muted))]">{data.subtitle}</p>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
                <tr>
                  {data.columns.map((c) => (
                    <th key={c.key} className="px-4 py-2">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={data.columns.length}
                      className="px-4 py-10 text-center text-[rgb(var(--color-muted))]"
                    >
                      No data.
                    </td>
                  </tr>
                ) : (
                  data.rows.map((row, i) => (
                    <tr
                      key={i}
                      className={
                        'border-t border-[rgb(var(--color-border))] ' +
                        (i % 2 ? 'bg-[rgb(var(--color-border))]/15' : '')
                      }
                    >
                      {data.columns.map((c) => (
                        <td
                          key={c.key}
                          className={
                            'px-4 py-2 ' +
                            (c.type === 'number' || c.type === 'int'
                              ? 'text-right tabular-nums'
                              : '')
                          }
                        >
                          {formatCell(row[c.key], c.type)}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <div className="border-t border-[rgb(var(--color-border))] px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
            {data.rows.length} row(s)
          </div>
        </div>
      )}
    </div>
  );
}

function formatCell(v: unknown, type: string): string {
  if (v === null || v === undefined || v === '') return '-';
  if (type === 'number') {
    const n = typeof v === 'number' ? v : Number(v);
    if (!Number.isNaN(n))
      return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (type === 'int') {
    const n = typeof v === 'number' ? v : Number(v);
    if (!Number.isNaN(n)) return n.toLocaleString();
  }
  if (type === 'datetime') return new Date(String(v)).toLocaleString();
  if (type === 'date') return String(v).slice(0, 10);
  return String(v);
}
