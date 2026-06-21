'use client';

import Link from 'next/link';
import { AlertTriangle, ChevronRight, Clock, UserCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Item = {
  id: number;
  case_no: string;
  customer_id: number;
  division_id: number;
  current_stage: string;
  status: string;
  stage_entered_at: string | null;
  sla_due_at: string | null;
  overdue: boolean;
  legal_filing_amount: string;
  assigned_to_me: boolean;
};

type Scope = 'all' | 'mine';

export default function ApprovalsInboxPage() {
  const [rows, setRows] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>('all');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    (async () => {
      try {
        const data = await api<Item[]>(
          scope === 'mine'
            ? '/api/v1/approvals/inbox?scope=mine'
            : '/api/v1/approvals/inbox',
        );
        if (!cancelled) setRows(data);
      } catch (e) {
        if (!cancelled) setErr((e as ApiError).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scope]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Approvals Inbox</h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Cases waiting for action at your stage.
        </p>
      </div>

      {/* Scope tabs: filter is now server-side so an empty "Assigned
          to me" tab means the user genuinely has nothing waiting
          rather than the client having silently dropped rows. */}
      <div className="inline-flex rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-1 shadow-soft">
        <Tab active={scope === 'all'} onClick={() => setScope('all')}>
          All open
        </Tab>
        <Tab active={scope === 'mine'} onClick={() => setScope('mine')}>
          <UserCheck className="mr-1 inline h-3.5 w-3.5" />
          Assigned to me
        </Tab>
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
              <th className="px-4 py-3">Stage</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">SLA</th>
              <th className="px-4 py-3">Entered Stage</th>
              <th className="px-4 py-3 text-right"></th>
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
                  {scope === 'mine'
                    ? 'Nothing assigned to you right now.'
                    : 'Inbox is clear.'}
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2 font-mono text-xs">
                    {r.case_no}
                    {r.assigned_to_me && (
                      <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-pug-gold-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-300">
                        <UserCheck className="h-3 w-3" /> You
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">{r.current_stage}</td>
                  <td className="px-4 py-2">{r.status}</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {Number(r.legal_filing_amount).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className="px-4 py-2">
                    {r.sla_due_at ? (
                      r.overdue ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-300">
                          <AlertTriangle className="h-3 w-3" /> Overdue
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-[rgb(var(--color-muted))]">
                          <Clock className="h-3 w-3" />
                          due {new Date(r.sla_due_at).toLocaleString()}
                        </span>
                      )
                    ) : (
                      <span className="text-xs text-[rgb(var(--color-muted))]">-</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                    {r.stage_entered_at ? new Date(r.stage_entered_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link
                      href={`/cases/${r.id}`}
                      className="inline-flex items-center gap-1 rounded bg-pug-navy-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-pug-navy-600"
                    >
                      Open <ChevronRight className="h-3 w-3" />
                    </Link>
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

function Tab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
        active
          ? 'bg-pug-gold-500 text-pug-navy-800'
          : 'text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40'
      }`}
    >
      {children}
    </button>
  );
}
