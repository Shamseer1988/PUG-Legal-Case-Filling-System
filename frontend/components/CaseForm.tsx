'use client';

import { Plus, Trash2, Save, Send, Printer, Paperclip, X } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';
import { CaseTimeline } from '@/components/CaseTimeline';
import { CaseActions } from '@/components/CaseActions';
import { CourtFilingPanel } from '@/components/CourtFilingPanel';
import { HearingsPanel } from '@/components/HearingsPanel';
import { CashRequestsPanel } from '@/components/CashRequestsPanel';
import { ClosurePanel } from '@/components/ClosurePanel';
import { PreviousAttachmentsModal } from '@/components/PreviousAttachmentsModal';

type ChequeDraft = {
  cheque_number: string;
  bank_id: number | null;
  bank_name_text: string;
  amount: string;
  cheque_date: string;
  cheque_type: string;
  bounce_reason: string;
};

type CaseDraft = {
  customer_id: number | null;
  division_id: number | null;
  salesman_id: number | null;
  bank_id: number | null;
  case_type_id: number | null;
  customer_type: string;
  actual_due_amount: string;
  legal_filing_amount: string;
  deposit_date: string;
  is_criminal: boolean;
  is_civil: boolean;
  commands: string;
  sales_manager_id: number | null;
  division_manager_id: number | null;
  auditor_id: number | null;
  fm_id: number | null;
  ed_id: number | null;
  chairman_id: number | null;
  lawyer_id: number | null;
  cheques: ChequeDraft[];
};

type CaseFull = {
  id: number;
  case_no: string;
  status: string;
  current_stage: string;
  attachments: {
    id: number;
    original_filename: string;
    size_bytes: number;
    mime_type: string;
    category: string;
  }[];
} & Record<string, unknown>;

const EMPTY_CHEQUE: ChequeDraft = {
  cheque_number: '',
  bank_id: null,
  bank_name_text: '',
  amount: '',
  cheque_date: '',
  cheque_type: 'Normal',
  bounce_reason: '',
};

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

const EMPTY_CASE: CaseDraft = {
  customer_id: null,
  division_id: null,
  salesman_id: null,
  bank_id: null,
  case_type_id: null,
  customer_type: 'Retail',
  actual_due_amount: '',
  legal_filing_amount: '',
  deposit_date: '',
  is_criminal: false,
  is_civil: false,
  commands: '',
  sales_manager_id: null,
  division_manager_id: null,
  auditor_id: null,
  fm_id: null,
  ed_id: null,
  chairman_id: null,
  lawyer_id: null,
  cheques: [{ ...EMPTY_CHEQUE }],
};

export function CaseForm({ caseId }: { caseId?: number }) {
  const router = useRouter();
  const me = useAuthStore((s) => s.me);
  const [logoErr, setLogoErr] = useState(false);

  const customers = useMasterOptions('/api/v1/masters/customers', 'name');
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');
  const salesmen = useMasterOptions('/api/v1/masters/salesmen', 'name');
  const banks = useMasterOptions('/api/v1/masters/banks', 'name');
  const caseTypes = useMasterOptions('/api/v1/masters/case-types', 'name');
  const lawyers = useMasterOptions('/api/v1/masters/lawyers', 'name');

  const [draft, setDraft] = useState<CaseDraft>(EMPTY_CASE);

  // Signatory dropdowns: division-scoped for the four operational
  // managers; cross-division for Auditor and Chairman / MD.
  const divisionScope = draft.division_id ? Number(draft.division_id) : null;
  const salesManagers = useUserOptions('Sales Manager', divisionScope);
  const divisionManagers = useUserOptions('Division Manager', divisionScope);
  const financeManagers = useUserOptions('Finance Manager', divisionScope);
  const executiveDirectors = useUserOptions('Executive Director', divisionScope);
  const auditors = useUserOptions('Auditor', null);
  const chairmen = useUserOptions('Chairman / MD', null);
  const [meta, setMeta] = useState<CaseFull | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const isEdit = caseId !== undefined;
  const locked = !!meta && meta.status !== 'Draft';
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const data = await api<CaseFull>(`/api/v1/cases/${caseId}`);
        setMeta(data);
        setDraft(toDraft(data));
      } catch (e) {
        setErr((e as ApiError).message);
      }
    })();
  }, [caseId, isEdit, reloadKey]);

  // Auto-pick signatories when there's exactly one candidate — common
  // for Auditor, Chairman / MD and small divisions where the user
  // shouldn't have to make a meaningless choice.
  useEffect(() => {
    if (locked) return;
    setDraft((d) => {
      const next = { ...d };
      const pairs: Array<[keyof CaseDraft, { value: number }[]]> = [
        ['sales_manager_id', salesManagers],
        ['division_manager_id', divisionManagers],
        ['fm_id', financeManagers],
        ['ed_id', executiveDirectors],
        ['auditor_id', auditors],
        ['chairman_id', chairmen],
      ];
      let changed = false;
      for (const [k, opts] of pairs) {
        if (next[k] == null && opts.length === 1) {
          (next[k] as number | null) = opts[0].value;
          changed = true;
        }
      }
      return changed ? next : d;
    });
  }, [
    locked,
    salesManagers,
    divisionManagers,
    financeManagers,
    executiveDirectors,
    auditors,
    chairmen,
  ]);

  const totalCheques = useMemo(
    () => draft.cheques.reduce((s, c) => s + Number(c.amount || 0), 0),
    [draft.cheques],
  );

  function up<K extends keyof CaseDraft>(k: K, v: CaseDraft[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }
  function upCheque(i: number, patch: Partial<ChequeDraft>) {
    setDraft((d) => {
      const cheques = d.cheques.map((c, idx) => (idx === i ? { ...c, ...patch } : c));
      return { ...d, cheques };
    });
  }
  function addCheque() {
    setDraft((d) => ({ ...d, cheques: [...d.cheques, { ...EMPTY_CHEQUE }] }));
  }
  function removeCheque(i: number) {
    setDraft((d) => ({
      ...d,
      cheques: d.cheques.length > 1 ? d.cheques.filter((_, idx) => idx !== i) : d.cheques,
    }));
  }

  function toPayload(): Record<string, unknown> {
    return {
      ...draft,
      customer_id: draft.customer_id ? Number(draft.customer_id) : undefined,
      division_id: draft.division_id ? Number(draft.division_id) : undefined,
      actual_due_amount: draft.actual_due_amount || '0',
      legal_filing_amount: draft.legal_filing_amount || '0',
      deposit_date: draft.deposit_date || null,
      cheques: draft.cheques
        .filter((c) => c.cheque_number.trim())
        .map((c) => ({
          ...c,
          amount: c.amount || '0',
          cheque_date: c.cheque_date || null,
        })),
    };
  }

  async function save(thenSubmit = false) {
    setBusy(true);
    setErr(null);
    setInfo(null);

    if (!draft.customer_id || !draft.division_id) {
      setErr('Customer and Division are required.');
      setBusy(false);
      return;
    }

    try {
      let id = caseId;
      if (id) {
        await api(`/api/v1/cases/${id}`, { method: 'PATCH', body: toPayload() });
      } else {
        const created = await api<CaseFull>('/api/v1/cases', {
          method: 'POST',
          body: toPayload(),
        });
        id = created.id;
      }
      if (thenSubmit) {
        await api(`/api/v1/cases/${id}/submit`, { method: 'POST' });
        setInfo(`Case submitted. Now awaiting Sales Manager approval.`);
      } else {
        setInfo('Draft saved.');
      }
      router.push(`/cases/${id}`);
      router.refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4 pb-12">
      {/* Brand banner */}
      <div className="rounded-xl border-b-2 border-pug-gold-500 bg-gradient-to-br from-pug-navy-800 via-pug-navy-600 to-pug-navy-500 px-6 py-4 text-white">
        <div className="flex items-center gap-3">
          {logoErr ? (
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pug-gold-500 text-sm font-extrabold text-pug-navy-800">
              PUG
            </div>
          ) : (
            <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded-full border border-white/20 bg-white/10">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${API_BASE}/api/v1/settings/public/logo`}
                alt="Logo"
                className="h-full w-full object-cover"
                onError={() => setLogoErr(true)}
              />
            </div>
          )}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-widest text-pug-gold-300">
              Paris United Group Holding
            </div>
            <div className="text-base font-semibold">Legal Case Application Form</div>
          </div>
          <div className="ml-auto text-right text-xs">
            <div>
              <strong>Case No:</strong> {meta?.case_no ?? '(auto on save)'}
            </div>
            <div>
              <strong>Status:</strong> {meta?.status ?? 'Draft'}
              {meta && ` · ${meta.current_stage}`}
            </div>
            <div>
              <strong>Date:</strong> {todayISO()}
            </div>
          </div>
        </div>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          {info}
        </div>
      )}

      {/* Workflow controls (only after Draft -> Submitted) */}
      {isEdit && meta && meta.status !== 'Draft' && (
        <>
          <PreviousAttachmentsModal caseId={meta.id} />
          <CaseTimeline
            caseId={meta.id}
            currentStage={meta.current_stage}
            status={meta.status}
          />
          <CaseActions
            caseId={meta.id}
            status={meta.status}
            currentStage={meta.current_stage}
            onDone={() => setReloadKey((k) => k + 1)}
          />
          {/* Phase 4 panels - visible once the case reaches Approved */}
          {(meta.status === 'Approved' ||
            meta.status === 'Filed' ||
            meta.status === 'Lawyer Approved') && (
            <>
              <CourtFilingPanel
                caseId={meta.id}
                status={meta.status}
                onChange={() => setReloadKey((k) => k + 1)}
              />
              <HearingsPanel caseId={meta.id} status={meta.status} />
              <CashRequestsPanel caseId={meta.id} status={meta.status} />
            </>
          )}
          {(meta.status === 'Approved' ||
            meta.status === 'Filed' ||
            meta.status === 'Lawyer Approved' ||
            meta.status === 'Closed') && (
            <ClosurePanel
              caseId={meta.id}
              status={meta.status}
              onChange={() => setReloadKey((k) => k + 1)}
            />
          )}
        </>
      )}

      <Card title="Case Filing">
        <div className="flex flex-wrap items-center gap-6">
          <Checkbox
            label="Criminal"
            value={draft.is_criminal}
            onChange={(v) => up('is_criminal', v)}
            disabled={locked}
          />
          <Checkbox
            label="Civil"
            value={draft.is_civil}
            onChange={(v) => up('is_civil', v)}
            disabled={locked}
          />
          <Checkbox
            label="Both"
            value={draft.is_criminal && draft.is_civil}
            onChange={(v) => {
              up('is_criminal', v);
              up('is_civil', v);
            }}
            disabled={locked}
          />
          <div className="ml-auto w-64">
            <Field label="Case Type">
              <Select
                value={draft.case_type_id}
                options={caseTypes}
                allowEmpty
                onChange={(v) => up('case_type_id', v)}
                disabled={locked}
              />
            </Field>
          </div>
        </div>
      </Card>

      <Card title="Customer &amp; Division">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label="Customer" required>
            <Select
              value={draft.customer_id}
              options={customers}
              allowEmpty
              onChange={(v) => up('customer_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Division" required>
            <Select
              value={draft.division_id}
              options={divisions}
              allowEmpty
              onChange={(v) => up('division_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Salesman">
            <Select
              value={draft.salesman_id}
              options={salesmen}
              allowEmpty
              onChange={(v) => up('salesman_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Customer Type">
            <select
              value={draft.customer_type}
              onChange={(e) => up('customer_type', e.target.value)}
              disabled={locked}
              className={inputCls}
            >
              <option>Retail</option>
              <option>Distribution</option>
              <option>Corporate</option>
            </select>
          </Field>
          <Field label="Bank (default)">
            <Select
              value={draft.bank_id}
              options={banks}
              allowEmpty
              onChange={(v) => up('bank_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Deposit Date">
            <input
              type="date"
              value={draft.deposit_date}
              onChange={(e) => up('deposit_date', e.target.value)}
              disabled={locked}
              className={inputCls}
            />
          </Field>
        </div>
      </Card>

      <Card title="Amounts">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label="Actual Due Amount">
            <input
              type="number"
              step="0.01"
              value={draft.actual_due_amount}
              onChange={(e) => up('actual_due_amount', e.target.value)}
              disabled={locked}
              className={inputCls}
            />
          </Field>
          <Field label="Legal Filing Amount">
            <input
              type="number"
              step="0.01"
              value={draft.legal_filing_amount}
              onChange={(e) => up('legal_filing_amount', e.target.value)}
              disabled={locked}
              className={inputCls}
            />
          </Field>
          <Field label="Cheques Total (computed)">
            <input
              readOnly
              value={totalCheques.toFixed(2)}
              className={inputCls + ' bg-[rgb(var(--color-border))]/30'}
            />
          </Field>
        </div>
      </Card>

      <Card
        title="Cheque Details"
        action={
          !locked && (
            <button
              onClick={addCheque}
              className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
            >
              <Plus className="h-3.5 w-3.5" /> Add Cheque
            </button>
          )
        }
      >
        <div className="space-y-3">
          {draft.cheques.map((c, i) => (
            <div
              key={i}
              className="grid grid-cols-1 gap-3 rounded-lg border border-[rgb(var(--color-border))] p-3 md:grid-cols-7"
            >
              <Field label="#" small>
                <input
                  readOnly
                  value={i + 1}
                  className={inputCls + ' bg-[rgb(var(--color-border))]/30 text-center'}
                />
              </Field>
              <Field label="Cheque Number" small>
                <input
                  value={c.cheque_number}
                  onChange={(e) => upCheque(i, { cheque_number: e.target.value })}
                  disabled={locked}
                  className={inputCls}
                />
              </Field>
              <Field label="Bank" small>
                <Select
                  value={c.bank_id}
                  options={banks}
                  allowEmpty
                  onChange={(v) => upCheque(i, { bank_id: v })}
                  disabled={locked}
                />
              </Field>
              <Field label="Amount" small>
                <input
                  type="number"
                  step="0.01"
                  value={c.amount}
                  onChange={(e) => upCheque(i, { amount: e.target.value })}
                  disabled={locked}
                  className={inputCls + ' text-right tabular-nums'}
                />
              </Field>
              <Field label="Date" small>
                <input
                  type="date"
                  value={c.cheque_date}
                  onChange={(e) => upCheque(i, { cheque_date: e.target.value })}
                  disabled={locked}
                  className={inputCls}
                />
              </Field>
              <Field label="Type" small>
                <select
                  value={c.cheque_type}
                  onChange={(e) => upCheque(i, { cheque_type: e.target.value })}
                  disabled={locked}
                  className={inputCls}
                >
                  <option>Normal</option>
                  <option>Guarantee</option>
                  <option>PDC</option>
                  <option>Post-Dated</option>
                </select>
              </Field>
              <Field label="Bounce Reason" small>
                <div className="flex gap-1">
                  <input
                    value={c.bounce_reason}
                    onChange={(e) => upCheque(i, { bounce_reason: e.target.value })}
                    disabled={locked}
                    className={inputCls}
                  />
                  {!locked && (
                    <button
                      type="button"
                      onClick={() => removeCheque(i)}
                      title="Remove cheque"
                      className="rounded-md border border-rose-500/40 px-2 text-xs text-rose-600 hover:bg-rose-500/10"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </Field>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Commands / Remarks">
        <textarea
          rows={4}
          value={draft.commands}
          onChange={(e) => up('commands', e.target.value)}
          disabled={locked}
          className={inputCls}
        />
      </Card>

      <Card title="Signatories">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label={`Accountant`}>
            <input readOnly value={me?.full_name ?? ''} className={inputCls + ' bg-[rgb(var(--color-border))]/30'} />
          </Field>
          <Field label="Sales Manager">
            <Select
              value={draft.sales_manager_id}
              options={salesManagers}
              allowEmpty
              onChange={(v) => up('sales_manager_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Division Manager">
            <Select
              value={draft.division_manager_id}
              options={divisionManagers}
              allowEmpty
              onChange={(v) => up('division_manager_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Auditor">
            <Select
              value={draft.auditor_id}
              options={auditors}
              allowEmpty
              onChange={(v) => up('auditor_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Finance Manager">
            <Select
              value={draft.fm_id}
              options={financeManagers}
              allowEmpty
              onChange={(v) => up('fm_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Executive Director">
            <Select
              value={draft.ed_id}
              options={executiveDirectors}
              allowEmpty
              onChange={(v) => up('ed_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Chairman / MD">
            <Select
              value={draft.chairman_id}
              options={chairmen}
              allowEmpty
              onChange={(v) => up('chairman_id', v)}
              disabled={locked}
            />
          </Field>
          <Field label="Lawyer">
            <Select
              value={draft.lawyer_id}
              options={lawyers}
              allowEmpty
              onChange={(v) => up('lawyer_id', v)}
              disabled={locked}
            />
          </Field>
        </div>
      </Card>

      {isEdit && meta && (
        <Card title="Attachments">
          <AttachmentManager caseId={meta.id} attachments={meta.attachments} locked={locked} onChange={(atts) => setMeta({ ...meta, attachments: atts })} />
        </Card>
      )}

      <div className="sticky bottom-0 -mx-6 border-t border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))]/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          {!locked && (
            <>
              <button
                onClick={() => save(false)}
                disabled={busy}
                className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-4 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
              >
                <Save className="h-4 w-4" /> {isEdit ? 'Save Changes' : 'Save Draft'}
              </button>
              {isEdit && (
                <button
                  onClick={() => save(true)}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-4 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
                >
                  <Send className="h-4 w-4" /> Save &amp; Submit
                </button>
              )}
            </>
          )}
          {isEdit && meta && (
            <Link
              href={`/cases/${meta.id}/print`}
              className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-4 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              <Printer className="h-4 w-4" /> Print
            </Link>
          )}
          {locked && (
            <div className="text-xs text-[rgb(var(--color-muted))]">
              Case is {meta?.status}; editing locked. Approvals continue in Phase 3.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// -------- helpers / sub-components --------

function toDraft(c: CaseFull): CaseDraft {
  const def = (v: unknown, fallback: string) => (v === null || v === undefined ? fallback : String(v));
  return {
    customer_id: (c.customer_id as number) ?? null,
    division_id: (c.division_id as number) ?? null,
    salesman_id: (c.salesman_id as number) ?? null,
    bank_id: (c.bank_id as number) ?? null,
    case_type_id: (c.case_type_id as number) ?? null,
    customer_type: def(c.customer_type, 'Retail'),
    actual_due_amount: def(c.actual_due_amount, ''),
    legal_filing_amount: def(c.legal_filing_amount, ''),
    deposit_date: def(c.deposit_date, ''),
    is_criminal: Boolean(c.is_criminal),
    is_civil: Boolean(c.is_civil),
    commands: def(c.commands, ''),
    sales_manager_id: (c.sales_manager_id as number) ?? null,
    division_manager_id: (c.division_manager_id as number) ?? null,
    auditor_id: (c.auditor_id as number) ?? null,
    fm_id: (c.fm_id as number) ?? null,
    ed_id: (c.ed_id as number) ?? null,
    chairman_id: (c.chairman_id as number) ?? null,
    lawyer_id: (c.lawyer_id as number) ?? null,
    cheques:
      Array.isArray(c.cheques) && c.cheques.length
        ? (c.cheques as ChequeDraft[]).map((ch) => ({
            cheque_number: ch.cheque_number ?? '',
            bank_id: ch.bank_id ?? null,
            bank_name_text: ch.bank_name_text ?? '',
            amount: String(ch.amount ?? ''),
            cheque_date: ch.cheque_date ?? '',
            cheque_type: ch.cheque_type ?? 'Normal',
            bounce_reason: ch.bounce_reason ?? '',
          }))
        : [{ ...EMPTY_CHEQUE }],
  };
}

/** Role-scoped signatory dropdown options.
 *
 * - For division-bound roles (Sales Manager, Division Manager, Finance
 *   Manager, Executive Director) we filter by the case's selected
 *   division so users only see candidates from their own division.
 * - For cross-division roles (Auditor, Chairman / MD) the backend
 *   ignores the division filter so they always show up.
 */
function useUserOptions(
  role: string,
  divisionId: number | null,
): { value: number; label: string }[] {
  const [opts, setOpts] = useState<{ value: number; label: string }[]>([]);
  useEffect(() => {
    const params = new URLSearchParams({ role });
    if (divisionId) params.set('division_id', String(divisionId));
    api<Array<{ id: number; full_name: string; email: string }>>(
      `/api/v1/users/options?${params.toString()}`,
    )
      .then((rows) =>
        setOpts(rows.map((r) => ({ value: r.id, label: `${r.full_name} (${r.email})` }))),
      )
      .catch(() => setOpts([]));
  }, [role, divisionId]);
  return opts;
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none disabled:opacity-60';

function Card({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Field({
  label,
  children,
  small,
  required,
}: {
  label: string;
  children: React.ReactNode;
  small?: boolean;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span
        className={
          'mb-1 block font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))] ' +
          (small ? 'text-[10px]' : 'text-xs')
        }
      >
        {label}
        {required && <span className="ml-1 text-rose-500">*</span>}
      </span>
      {children}
    </label>
  );
}

function Checkbox({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="h-4 w-4"
      />
      {label}
    </label>
  );
}

function Select({
  value,
  options,
  onChange,
  allowEmpty,
  disabled,
}: {
  value: number | null;
  options: { value: number; label: string }[];
  onChange: (v: number | null) => void;
  allowEmpty?: boolean;
  disabled?: boolean;
}) {
  return (
    <select
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      disabled={disabled}
      className={inputCls}
    >
      {allowEmpty && <option value="">--</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function AttachmentManager({
  caseId,
  attachments,
  locked,
  onChange,
}: {
  caseId: number;
  attachments: CaseFull['attachments'];
  locked: boolean;
  onChange: (atts: CaseFull['attachments']) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function upload(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    setErr(null);
    try {
      const updated = [...attachments];
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('category', 'Supporting Document');
        const token = useAuthStore.getState().accessToken;
        const r = await fetch(`${API_BASE}/api/v1/cases/${caseId}/attachments`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: fd,
        });
        if (!r.ok) {
          throw new Error((await r.json()).detail || 'Upload failed');
        }
        updated.push(await r.json());
      }
      onChange(updated);
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm('Remove this attachment?')) return;
    try {
      await api(`/api/v1/cases/${caseId}/attachments/${id}`, { method: 'DELETE' });
      onChange(attachments.filter((a) => a.id !== id));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function downloadOne(att: CaseFull['attachments'][number]) {
    try {
      const token = useAuthStore.getState().accessToken;
      const r = await fetch(
        `${API_BASE}/api/v1/cases/${caseId}/attachments/${att.id}/download`,
        { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
      );
      if (!r.ok) throw new Error(`Download failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = att.original_filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function downloadZip() {
    try {
      const token = useAuthStore.getState().accessToken;
      const r = await fetch(`${API_BASE}/api/v1/cases/${caseId}/attachments.zip`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!r.ok) throw new Error(`ZIP failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `case-${caseId}-attachments.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {!locked && (
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40">
            <Paperclip className="h-4 w-4" />
            {busy ? 'Uploading...' : 'Attach Files'}
            <input
              type="file"
              multiple
              disabled={busy}
              onChange={(e) => upload(e.target.files)}
              className="hidden"
            />
          </label>
        )}
        {attachments.length > 0 && (
          <button
            type="button"
            onClick={downloadZip}
            className="inline-flex items-center gap-2 rounded-md border border-pug-gold-500/40 bg-pug-gold-500/10 px-3 py-2 text-sm font-semibold text-pug-gold-700 hover:bg-pug-gold-500/20 dark:text-pug-gold-300"
          >
            <Paperclip className="h-4 w-4" /> Download all as ZIP ({attachments.length})
          </button>
        )}
      </div>
      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {attachments.length === 0 ? (
        <div className="text-xs text-[rgb(var(--color-muted))]">No attachments yet.</div>
      ) : (
        <ul className="divide-y divide-[rgb(var(--color-border))] rounded-md border border-[rgb(var(--color-border))] text-sm">
          {attachments.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-3 py-2">
              <Paperclip className="h-4 w-4 text-[rgb(var(--color-muted))]" />
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => downloadOne(a)}
                  className="truncate text-left font-medium hover:underline"
                >
                  {a.original_filename}
                </button>
                <div className="text-[10px] text-[rgb(var(--color-muted))]">
                  {a.category} &middot; {(a.size_bytes / 1024).toFixed(1)} KB
                </div>
              </div>
              {!locked && (
                <button
                  onClick={() => remove(a.id)}
                  className="rounded p-1 text-xs text-rose-600 hover:bg-rose-500/10"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
