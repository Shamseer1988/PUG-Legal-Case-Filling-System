'use client';

import Link from 'next/link';
import { Plus, FileText, Printer } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';

type Row = {
  id: number;
  case_no: string;
  customer_id: number;
  division_id: number;
  status: string;
  current_stage: string;
  legal_filing_amount: string;
  is_criminal: boolean;
  is_civil: boolean;
  created_at: string;
  submitted_at: string | null;
};

const STATUS_COLOR: Record<string, string> = {
  Draft: 'bg-slate-500/15 text-slate-700 border-slate-500/40 dark:text-slate-300',
  Submitted: 'bg-pug-gold-500/20 text-pug-gold-700 border-pug-gold-500/40 dark:text-pug-gold-300',
};

export default function CasesListPage() {
  const me = useAuthStore((s) => s.me);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setRows(await api<Row[]>('/api/v1/cases'));
      } catch (e) {
        setErr((e as ApiError).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Cases</h1>
        {hasPermission(me, 'cases:create') && (
          <Link
            href="/cases/new"
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-4 w-4" /> New Case
          </Link>
        )}
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
              <th className="px-4 py-3">Case No</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Legal Amount</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Stage</th>
              <th className="px-4 py-3">Created</th>
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
                  No cases yet. Click <strong>New Case</strong> to file the first one.
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const types = [r.is_criminal && 'Criminal', r.is_civil && 'Civil']
                  .filter(Boolean)
                  .join(' + ');
                return (
                  <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                    <td className="px-4 py-2 font-mono text-xs">{r.case_no}</td>
                    <td className="px-4 py-2">{types || '-'}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {Number(r.legal_filing_amount).toLocaleString(undefined, {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={
                          'inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
                          (STATUS_COLOR[r.status] ?? 'bg-slate-500/15 text-slate-600 border-slate-500/40')
                        }
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                      {r.current_stage}
                    </td>
                    <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Link
                        href={`/cases/${r.id}`}
                        className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                      >
                        <FileText className="h-3 w-3" /> Open
                      </Link>
                      <Link
                        href={`/cases/${r.id}/print`}
                        target="_blank"
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                      >
                        <Printer className="h-3 w-3" /> Print
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
