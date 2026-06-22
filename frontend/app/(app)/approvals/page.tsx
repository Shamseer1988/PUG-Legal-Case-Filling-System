'use client';

import Link from 'next/link';
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Clock,
  HelpCircle,
  Send,
  UserCheck,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
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
type BulkAction = 'approve' | 'reject' | 'request_clarification';

type BulkResult = {
  succeeded: number;
  failed: number;
  items: { case_id: number; case_no: string; ok: boolean; detail: string }[];
};

export default function ApprovalsInboxPage() {
  const [rows, setRows] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope>('all');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkAction, setBulkAction] = useState<BulkAction | null>(null);
  const [bulkComment, setBulkComment] = useState('');
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkResult, setBulkResult] = useState<BulkResult | null>(null);

  async function reload() {
    setLoading(true);
    setErr(null);
    try {
      const data = await api<Item[]>(
        scope === 'mine'
          ? '/api/v1/approvals/inbox?scope=mine'
          : '/api/v1/approvals/inbox',
      );
      setRows(data);
      setSelected(new Set());
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

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
        if (!cancelled) {
          setRows(data);
          setSelected(new Set());
        }
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

  function toggleOne(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const allVisibleSelected = useMemo(
    () => rows.length > 0 && rows.every((r) => selected.has(r.id)),
    [rows, selected],
  );

  function toggleAll() {
    if (allVisibleSelected) setSelected(new Set());
    else setSelected(new Set(rows.map((r) => r.id)));
  }

  async function runBulk() {
    if (!bulkAction || selected.size === 0) return;
    const needComment = bulkAction === 'reject' || bulkAction === 'request_clarification';
    if (needComment && !bulkComment.trim()) {
      setErr(`A comment is required for ${bulkAction}.`);
      return;
    }
    setBulkBusy(true);
    setErr(null);
    setBulkResult(null);
    try {
      const r = await api<BulkResult>('/api/v1/approvals/bulk-transition', {
        method: 'POST',
        body: {
          case_ids: Array.from(selected),
          action: bulkAction,
          comment: bulkComment,
        },
      });
      setBulkResult(r);
      setBulkAction(null);
      setBulkComment('');
      await reload();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Approvals Inbox</h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Cases waiting for action at your stage.
        </p>
      </div>

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

      {bulkResult && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm">
          <strong>{bulkResult.succeeded}</strong> case(s) processed.
          {bulkResult.failed > 0 && (
            <>
              {' '}
              <strong>{bulkResult.failed}</strong> failed:
              <ul className="ml-4 mt-1 list-disc text-xs">
                {bulkResult.items
                  .filter((i) => !i.ok)
                  .slice(0, 10)
                  .map((i) => (
                    <li key={i.case_id}>
                      {i.case_no || `Case #${i.case_id}`}: {i.detail}
                    </li>
                  ))}
              </ul>
            </>
          )}
          <button
            type="button"
            onClick={() => setBulkResult(null)}
            className="ml-2 underline"
          >
            dismiss
          </button>
        </div>
      )}

      {/* Bulk toolbar: only renders when at least one row is checked */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-pug-gold-500/40 bg-pug-gold-500/5 px-3 py-2 text-sm">
          <span className="font-semibold">{selected.size} selected</span>
          <button
            type="button"
            onClick={() => {
              setBulkAction('approve');
              setBulkComment('');
            }}
            className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
          >
            <Check className="h-3.5 w-3.5" /> Approve
          </button>
          <button
            type="button"
            onClick={() => {
              setBulkAction('request_clarification');
              setBulkComment('');
            }}
            className="inline-flex items-center gap-1 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <HelpCircle className="h-3.5 w-3.5" /> Request Clarification
          </button>
          <button
            type="button"
            onClick={() => {
              setBulkAction('reject');
              setBulkComment('');
            }}
            className="inline-flex items-center gap-1 rounded-md bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500"
          >
            <X className="h-3.5 w-3.5" /> Reject
          </button>
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="ml-auto rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
          >
            Clear
          </button>
        </div>
      )}

      {bulkAction && (
        <div className="rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-3 text-sm shadow-soft">
          <div className="mb-2 font-semibold">
            Confirm bulk{' '}
            {bulkAction === 'approve'
              ? 'approval'
              : bulkAction === 'reject'
                ? 'rejection'
                : 'clarification request'}{' '}
            for {selected.size} case(s)
          </div>
          <textarea
            rows={3}
            value={bulkComment}
            onChange={(e) => setBulkComment(e.target.value)}
            placeholder={
              bulkAction === 'approve'
                ? 'Comment (optional) - applied to every selected case'
                : bulkAction === 'reject'
                  ? 'Rejection reason (required) - applied to every selected case'
                  : 'What clarification do you need? (required) - applied to every selected case'
            }
            className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={runBulk}
              disabled={bulkBusy}
              className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-50 ${
                bulkAction === 'reject'
                  ? 'bg-rose-600 text-white hover:bg-rose-500'
                  : bulkAction === 'request_clarification'
                    ? 'bg-pug-gold-500 text-pug-navy-800 hover:bg-pug-gold-400'
                    : 'bg-emerald-600 text-white hover:bg-emerald-500'
              }`}
            >
              <Send className="h-4 w-4" />
              {bulkBusy ? 'Working...' : `Confirm for ${selected.size} case(s)`}
            </button>
            <button
              type="button"
              onClick={() => {
                setBulkAction(null);
                setBulkComment('');
              }}
              className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <table className="w-full text-sm">
          <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <tr>
              <th className="px-3 py-3 w-8">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={allVisibleSelected}
                  onChange={toggleAll}
                  disabled={rows.length === 0}
                />
              </th>
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
                <td colSpan={8} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  Loading...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-[rgb(var(--color-muted))]">
                  {scope === 'mine'
                    ? 'Nothing assigned to you right now.'
                    : 'Inbox is clear.'}
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ${r.case_no}`}
                      checked={selected.has(r.id)}
                      onChange={() => toggleOne(r.id)}
                    />
                  </td>
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
