'use client';

import Link from 'next/link';
import { Check, Wallet, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';

type CashRequest = {
  id: number;
  case_id: number;
  case_no: string;
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

const STATUSES = ['', 'Requested', 'Approved', 'Rejected', 'Paid'];

export default function CashRequestsInboxPage() {
  const me = useAuthStore((s) => s.me);
  const canApprove = hasPermission(me, 'expenses:approve');
  const canPay = hasPermission(me, 'expenses:pay');

  const [rows, setRows] = useState<CashRequest[]>([]);
  const [filter, setFilter] = useState<string>('Requested');
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const q = filter ? `?only=${encodeURIComponent(filter)}` : '';
      setRows(await api<CashRequest[]>(`/api/v1/cash-requests${q}`));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
  }, [filter]);

  async function approve(id: number) {
    const c = prompt('Approval comment (optional):') ?? '';
    try {
      await api(`/api/v1/cash-requests/${id}/approve`, { method: 'POST', body: { comment: c } });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }
  async function reject(id: number) {
    const c = prompt('Rejection reason (required):');
    if (!c) return;
    try {
      await api(`/api/v1/cash-requests/${id}/reject`, { method: 'POST', body: { comment: c } });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }
  async function pay(id: number) {
    const ref = prompt('Payment reference / voucher #:') ?? '';
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
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Cash Requests</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Lawyer requests, FM approvals, and Accountant payments across cases.
          </p>
        </div>
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
              <th className="px-4 py-3">Case</th>
              <th className="px-4 py-3">Amount</th>
              <th className="px-4 py-3">Purpose</th>
              <th className="px-4 py-3">Requested By</th>
              <th className="px-4 py-3">Approved</th>
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
                <td colSpan={7} className="px-4 py-8 text-center text-[rgb(var(--color-muted))]">
                  Nothing in this view.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2">{r.status}</td>
                  <td className="px-4 py-2 font-mono text-xs">
                    <Link href={`/cases/${r.case_id}`} className="hover:underline">
                      {r.case_no}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {Number(r.amount).toFixed(2)}
                  </td>
                  <td className="px-4 py-2">{r.purpose || '-'}</td>
                  <td className="px-4 py-2 text-xs">
                    {r.requested_by_name}
                    <div className="text-[10px] text-[rgb(var(--color-muted))]">
                      {r.requested_at && new Date(r.requested_at).toLocaleString()}
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {r.approved_by_name || '-'}
                    {r.approval_comment && (
                      <div className="text-[10px] italic">"{r.approval_comment}"</div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
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
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
