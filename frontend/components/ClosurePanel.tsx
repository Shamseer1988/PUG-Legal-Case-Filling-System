'use client';

import { CheckCircle2, FileCheck, Lock, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';

type Closure = {
  id: number;
  case_id: number;
  closure_type: string;
  command: string;
  settled_amount: string;
  settled_date: string | null;
  court_cheque_number: string;
  court_cheque_bank: string;
  court_cheque_date: string | null;
  transfer_reference: string;
  transfer_bank: string;
  transfer_account_last4: string;
  cash_receipt_no: string;
  settlement_agreement_ref: string;
  writeoff_reason: string;
  closed_by_name: string;
  closed_at: string;
};

const TYPES: { value: string; label: string }[] = [
  { value: 'court_cheque', label: 'Court Cheque Received' },
  { value: 'online_transfer', label: 'Online Transfer' },
  { value: 'cash_received', label: 'Cash Received' },
  { value: 'settlement', label: 'Settlement Agreement' },
  { value: 'writeoff', label: 'Write-Off' },
  { value: 'other', label: 'Other' },
];

type Props = { caseId: number; status: string; onChange: () => void };

export function ClosurePanel({ caseId, status, onChange }: Props) {
  const me = useAuthStore((s) => s.me);
  const canClose = hasPermission(me, 'cases:create');
  const [closure, setClosure] = useState<Closure | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState({
    closure_type: 'court_cheque',
    command: '',
    settled_amount: '',
    settled_date: '',
    court_cheque_number: '',
    court_cheque_bank: '',
    court_cheque_date: '',
    transfer_reference: '',
    transfer_bank: '',
    transfer_account_last4: '',
    cash_receipt_no: '',
    settlement_agreement_ref: '',
    writeoff_reason: '',
  });

  async function load() {
    try {
      const c = await api<Closure | null>(`/api/v1/cases/${caseId}/closure`);
      setClosure(c);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoaded(true);
    }
  }
  useEffect(() => {
    load();
  }, [caseId]);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const payload = {
        ...draft,
        settled_amount: draft.settled_amount || '0',
        settled_date: draft.settled_date || null,
        court_cheque_date: draft.court_cheque_date || null,
      };
      const c = await api<Closure>(`/api/v1/cases/${caseId}/close`, {
        method: 'POST',
        body: payload,
      });
      setClosure(c);
      onChange();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  // Hide entirely if the case can't yet be closed and there's no existing closure
  const closable = status === 'Approved' || status === 'Filed';
  if (!loaded) return null;
  if (!closure && !closable && status !== 'Closed') return null;

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <Lock className="h-4 w-4 text-pug-gold-700 dark:text-pug-gold-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Closure
        </h2>
        {closure && (
          <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Closed
          </span>
        )}
      </div>

      {err && (
        <div className="mb-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {closure ? (
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <Pair k="Type" v={TYPES.find((t) => t.value === closure.closure_type)?.label ?? closure.closure_type} />
          <Pair
            k="Settled Amount"
            v={Number(closure.settled_amount).toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          />
          <Pair k="Settled Date" v={closure.settled_date ?? '-'} />
          <Pair k="Closed By" v={closure.closed_by_name} />
          {closure.closure_type === 'court_cheque' && (
            <>
              <Pair k="Court Cheque #" v={closure.court_cheque_number || '-'} />
              <Pair k="Court Cheque Bank" v={closure.court_cheque_bank || '-'} />
              <Pair k="Court Cheque Date" v={closure.court_cheque_date ?? '-'} />
            </>
          )}
          {closure.closure_type === 'online_transfer' && (
            <>
              <Pair k="Transfer Reference" v={closure.transfer_reference || '-'} />
              <Pair k="Transfer Bank" v={closure.transfer_bank || '-'} />
              <Pair k="Account (last 4)" v={closure.transfer_account_last4 || '-'} />
            </>
          )}
          {closure.closure_type === 'cash_received' && (
            <Pair k="Cash Receipt No." v={closure.cash_receipt_no || '-'} />
          )}
          {closure.closure_type === 'settlement' && (
            <Pair k="Agreement Ref." v={closure.settlement_agreement_ref || '-'} />
          )}
          {closure.closure_type === 'writeoff' && (
            <div className="md:col-span-2">
              <Label>Write-off Reason</Label>
              <Note>{closure.writeoff_reason || '-'}</Note>
            </div>
          )}
          <div className="md:col-span-2">
            <Label>Command / Note</Label>
            <Note>{closure.command || '-'}</Note>
          </div>
        </dl>
      ) : closable && canClose ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Field label="Closure Type" required>
              <select
                value={draft.closure_type}
                onChange={(e) => setDraft({ ...draft, closure_type: e.target.value })}
                className={inputCls}
              >
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Settled Amount">
              <input
                type="number"
                step="0.01"
                value={draft.settled_amount}
                onChange={(e) => setDraft({ ...draft, settled_amount: e.target.value })}
                className={inputCls + ' text-right tabular-nums'}
              />
            </Field>
            <Field label="Settled Date">
              <input
                type="date"
                value={draft.settled_date}
                onChange={(e) => setDraft({ ...draft, settled_date: e.target.value })}
                className={inputCls}
              />
            </Field>

            {draft.closure_type === 'court_cheque' && (
              <>
                <Field label="Court Cheque Number" required>
                  <input
                    value={draft.court_cheque_number}
                    onChange={(e) =>
                      setDraft({ ...draft, court_cheque_number: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="Court Cheque Bank">
                  <input
                    value={draft.court_cheque_bank}
                    onChange={(e) =>
                      setDraft({ ...draft, court_cheque_bank: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="Court Cheque Date">
                  <input
                    type="date"
                    value={draft.court_cheque_date}
                    onChange={(e) =>
                      setDraft({ ...draft, court_cheque_date: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            {draft.closure_type === 'online_transfer' && (
              <>
                <Field label="Transfer Reference" required>
                  <input
                    value={draft.transfer_reference}
                    onChange={(e) =>
                      setDraft({ ...draft, transfer_reference: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="Transfer Bank">
                  <input
                    value={draft.transfer_bank}
                    onChange={(e) =>
                      setDraft({ ...draft, transfer_bank: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
                <Field label="Account (last 4)">
                  <input
                    maxLength={8}
                    value={draft.transfer_account_last4}
                    onChange={(e) =>
                      setDraft({ ...draft, transfer_account_last4: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
              </>
            )}

            {draft.closure_type === 'cash_received' && (
              <Field label="Cash Receipt No." required>
                <input
                  value={draft.cash_receipt_no}
                  onChange={(e) => setDraft({ ...draft, cash_receipt_no: e.target.value })}
                  className={inputCls}
                />
              </Field>
            )}

            {draft.closure_type === 'settlement' && (
              <Field label="Settlement Agreement Reference" required>
                <input
                  value={draft.settlement_agreement_ref}
                  onChange={(e) =>
                    setDraft({ ...draft, settlement_agreement_ref: e.target.value })
                  }
                  className={inputCls}
                />
              </Field>
            )}

            {draft.closure_type === 'writeoff' && (
              <div className="md:col-span-2">
                <Field label="Write-off Reason" required>
                  <textarea
                    rows={2}
                    value={draft.writeoff_reason}
                    onChange={(e) =>
                      setDraft({ ...draft, writeoff_reason: e.target.value })
                    }
                    className={inputCls}
                  />
                </Field>
              </div>
            )}
          </div>

          <Field label="Command / Closure Note" required>
            <textarea
              rows={3}
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              className={inputCls}
              placeholder="How was the case settled? Any conditions?"
            />
          </Field>

          <div>
            <button
              onClick={save}
              disabled={busy}
              className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
            >
              <FileCheck className="h-4 w-4" /> Close Case
            </button>
            <div className="mt-1 text-[10px] text-rose-600">
              Closing is final. The case will be locked from further edits.
            </div>
          </div>
        </div>
      ) : (
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Available after Chairman / MD approval.
        </div>
      )}
    </section>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <Label>
        {label}
        {required && <span className="ml-1 text-rose-500">*</span>}
      </Label>
      {children}
    </label>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
      {children}
    </span>
  );
}

function Pair({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <Label>{k}</Label>
      <div className="text-sm">{v}</div>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/20 px-3 py-2 text-sm">
      {children}
    </div>
  );
}
