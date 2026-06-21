'use client';

import { Banknote, Check, Plus, Send, Wallet, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { ACTION, canDoAction, useCapabilitiesStore } from '@/lib/capabilities';

type CashRequest = {
  id: number;
  case_id: number;
  amount: string;
  purpose: string;
  status: 'Requested' | 'Approved' | 'Rejected' | 'Paid';
  requested_by_name: string;
  requested_at: string | null;
  approved_by_name: string;
  approved_at: string | null;
  approval_comment: string;
  paid_by_name: string;
  paid_at: string | null;
  payment_reference: string;
};

type Summary = {
  total_requested: string;
  total_approved: string;
  total_paid: string;
  open_count: number;
};

type Props = { caseId: number; status: string };

export function CashRequestsPanel({ caseId, status }: Props) {
  const caps = useCapabilitiesStore((s) => s.caps);
  const canRequest = canDoAction(caps, ACTION.CASH_REQUEST);
  const canApprove = canDoAction(caps, ACTION.CASH_APPROVE);
  const canPay = canDoAction(caps, ACTION.CASH_PAY);

  const [rows, setRows] = useState<CashRequest[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ amount: '', purpose: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const [items, sum] = await Promise.all([
        api<CashRequest[]>(`/api/v1/cases/${caseId}/cash-requests`),
        api<Summary>(`/api/v1/cases/${caseId}/spend-summary`),
      ]);
      setRows(items);
      setSummary(sum);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    load();
  }, [caseId]);

  const blocked =
    status !== 'Approved' &&
    status !== 'Filed' &&
    status !== 'Lawyer Approved';

  async function create() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/cases/${caseId}/cash-requests`, {
        method: 'POST',
        body: { amount: draft.amount, purpose: draft.purpose },
      });
      setAdding(false);
      setDraft({ amount: '', purpose: '' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function approve(id: number) {
    const comment = prompt('Approval comment (optional):') ?? '';
    try {
      await api(`/api/v1/cash-requests/${id}/approve`, {
        method: 'POST',
        body: { comment },
      });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function reject(id: number) {
    const comment = prompt('Rejection reason (required):');
    if (!comment) return;
    try {
      await api(`/api/v1/cash-requests/${id}/reject`, {
        method: 'POST',
        body: { comment },
      });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function pay(id: number) {
    const ref = prompt('Payment reference (e.g. voucher / receipt #):') ?? '';
    try {
      await api(`/api/v1/cash-requests/${id}/pay`, {
        method: 'POST',
        body: { payment_reference: ref },
      });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Banknote className="h-4 w-4 text-pug-gold-700 dark:text-pug-gold-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Cash Requests &amp; Expenses
        </h2>
        {summary && (
          <span className="ml-2 text-xs text-[rgb(var(--color-muted))]">
            Paid: <strong>{Number(summary.total_paid).toFixed(2)}</strong> &middot; Approved:{' '}
            {Number(summary.total_approved).toFixed(2)} &middot; Open:{' '}
            {summary.open_count}
          </span>
        )}
        {canRequest && !adding && !blocked && (
          <button
            onClick={() => setAdding(true)}
            className="ml-auto flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-3.5 w-3.5" /> Request Cash
          </button>
        )}
      </div>

      {blocked && (
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Available after Chairman / MD approval.
        </div>
      )}

      {err && (
        <div className="mb-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {adding && (
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-[rgb(var(--color-border))] p-3 md:grid-cols-3">
          <Field label="Amount">
            <input
              type="number"
              step="0.01"
              value={draft.amount}
              onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
              className={inputCls + ' text-right tabular-nums'}
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="Purpose">
              <input
                value={draft.purpose}
                onChange={(e) => setDraft({ ...draft, purpose: e.target.value })}
                placeholder="e.g. Court fees, process server"
                className={inputCls}
              />
            </Field>
          </div>
          <div className="md:col-span-3 flex gap-2">
            <button
              onClick={create}
              disabled={busy || !draft.amount}
              className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
            >
              <Send className="h-4 w-4" /> Send Request
            </button>
            <button
              onClick={() => setAdding(false)}
              className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="text-xs text-[rgb(var(--color-muted))]">No cash requests yet.</div>
      ) : (
        <div className="overflow-hidden rounded-md border border-[rgb(var(--color-border))]">
          <table className="w-full text-sm">
            <thead className="bg-[rgb(var(--color-border))]/30 text-left text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
              <tr>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Amount</th>
                <th className="px-3 py-2">Purpose</th>
                <th className="px-3 py-2">Requested</th>
                <th className="px-3 py-2">Approved</th>
                <th className="px-3 py-2">Paid</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-3 py-2">
                    <StatusBadge s={r.status} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {Number(r.amount).toFixed(2)}
                  </td>
                  <td className="px-3 py-2">{r.purpose || '-'}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.requested_by_name}
                    <div className="text-[10px] text-[rgb(var(--color-muted))]">
                      {r.requested_at && new Date(r.requested_at).toLocaleString()}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.approved_by_name || '-'}
                    <div className="text-[10px] text-[rgb(var(--color-muted))]">
                      {r.approved_at && new Date(r.approved_at).toLocaleString()}
                    </div>
                    {r.approval_comment && (
                      <div className="text-[10px] italic">"{r.approval_comment}"</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.paid_by_name || '-'}
                    <div className="text-[10px] text-[rgb(var(--color-muted))]">
                      {r.paid_at && new Date(r.paid_at).toLocaleString()}
                    </div>
                    {r.payment_reference && (
                      <div className="text-[10px]">ref: {r.payment_reference}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.status === 'Requested' && canApprove && (
                      <>
                        <button
                          onClick={() => approve(r.id)}
                          className="mr-1 inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-emerald-500"
                        >
                          <Check className="h-3 w-3" /> Approve
                        </button>
                        <button
                          onClick={() => reject(r.id)}
                          className="inline-flex items-center gap-1 rounded bg-rose-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-500"
                        >
                          <X className="h-3 w-3" /> Reject
                        </button>
                      </>
                    )}
                    {r.status === 'Approved' && canPay && (
                      <button
                        onClick={() => pay(r.id)}
                        className="inline-flex items-center gap-1 rounded bg-pug-gold-500 px-2 py-1 text-[11px] font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
                      >
                        <Wallet className="h-3 w-3" /> Pay
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}

function StatusBadge({ s }: { s: CashRequest['status'] }) {
  const cls = {
    Requested:
      'bg-pug-gold-500/20 text-pug-gold-700 dark:text-pug-gold-300 border-pug-gold-500/40',
    Approved: 'bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-500/40',
    Rejected: 'bg-rose-500/20 text-rose-700 dark:text-rose-300 border-rose-500/40',
    Paid: 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40',
  }[s];
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${cls}`}
    >
      {s}
    </span>
  );
}
