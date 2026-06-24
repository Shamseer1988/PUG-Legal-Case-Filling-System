'use client';

import { Plus, Trash2, Save, Send, Printer } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { ACTION, canDoAction, useCapabilitiesStore } from '@/lib/capabilities';
import { useMasterOptions } from '@/lib/useMasters';
import { CaseTimeline } from '@/components/CaseTimeline';
import { CaseActions } from '@/components/CaseActions';
import { CourtFilingPanel } from '@/components/CourtFilingPanel';
import { HearingsPanel } from '@/components/HearingsPanel';
import { CashRequestsPanel } from '@/components/CashRequestsPanel';
import { ClosurePanel } from '@/components/ClosurePanel';
import { PreviousAttachmentsModal } from '@/components/PreviousAttachmentsModal';
import { SignedFormPanel } from '@/components/SignedFormPanel';
import { CategorizedAttachments } from '@/components/CategorizedAttachments';
import { ChequeAttachmentButton } from '@/components/ChequeAttachmentButton';

type ChequeDraft = {
  // The DB row id, set after the case has been saved at least once.
  // Required for cheque-level attachment uploads.
  id?: number;
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
  const caps = useCapabilitiesStore((s) => s.caps);
  const [logoErr, setLogoErr] = useState(false);

  const customers = useMasterOptions('/api/v1/masters/customers', 'name');
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');
  const salesmen = useMasterOptions('/api/v1/masters/salesmen', 'name');
  const banks = useMasterOptions('/api/v1/masters/banks', 'name');
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
  // Phase 39: the Accountant can keep editing the case while it's
  // still sitting at Sales Manager (status=Submitted) and SM hasn't
  // acted yet. As soon as any approver acts (Approve / Reject /
  // Clarify), the stage or status flips and the case locks. The
  // backend enforces the same rule - this is just the matching UI
  // gate so the inputs aren't grey when the user can actually save.
  const editableAtSalesMgr =
    !!meta &&
    meta.status === 'Submitted' &&
    meta.current_stage === 'Sales Manager' &&
    me?.id === (meta.created_by_id as number | undefined);
  const locked = !!meta && meta.status !== 'Draft' && !editableAtSalesMgr;
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

  // Phase 39: on a brand-new case the Accountant's division is
  // auto-filled from their division mapping. If they're mapped
  // to exactly one division we lock it in; if they're mapped to
  // many, we pre-pick the first so the dependent dropdowns
  // (customer, signatories) have something to scope by - the
  // user can still pick a different one before saving.
  useEffect(() => {
    if (isEdit) return;
    const mine = caps?.divisions ?? [];
    if (mine.length === 0) return;
    setDraft((d) => (d.division_id == null ? { ...d, division_id: mine[0] } : d));
  }, [isEdit, caps?.divisions]);

  // Phase 39: when the user picks a customer, mirror the customer's
  // mapped salesman + division onto the draft. The salesman is set
  // up under Customer master, so re-typing it on every case is
  // wasteful (and error-prone). The user can still override either
  // field after auto-fill by editing the dropdown.
  useEffect(() => {
    const cid = draft.customer_id;
    if (!cid || locked) return;
    let cancelled = false;
    (async () => {
      try {
        const cust = await api<{
          id: number;
          division_id: number | null;
          salesman_id: number | null;
        }>(`/api/v1/masters/customers/${cid}`);
        if (cancelled) return;
        setDraft((d) => {
          // Only touch fields the user hasn't already set so we
          // don't clobber a deliberate override.
          const next = { ...d };
          if (cust.salesman_id && next.salesman_id == null) {
            next.salesman_id = cust.salesman_id;
          }
          if (cust.division_id && next.division_id == null) {
            next.division_id = cust.division_id;
          }
          return next;
        });
      } catch {
        /* customer detail fetch is best-effort */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [draft.customer_id, locked]);

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
      // Phase 38: persist every cheque row, even those without a
      // number, so each row gets a server-side id and the cheque-
      // copy paperclip becomes attachable right after Save. Submit
      // (not save) enforces non-empty numbers.
      //
      // CRITICAL: send each row's id so the backend can diff-
      // merge instead of clear-and-rebuild. Without this, every
      // PATCH cascade-deletes the ChequeAttachment rows linked to
      // the cheques.
      cheques: draft.cheques.map((c) => ({
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
      let saved: CaseFull;
      if (id) {
        saved = await api<CaseFull>(`/api/v1/cases/${id}`, {
          method: 'PATCH',
          body: toPayload(),
        });
      } else {
        saved = await api<CaseFull>('/api/v1/cases', {
          method: 'POST',
          body: toPayload(),
        });
        id = saved.id;
      }
      if (thenSubmit) {
        // Submit returns the post-transition CaseRead; use that
        // for the same local-state refresh.
        saved = await api<CaseFull>(`/api/v1/cases/${id}/submit`, {
          method: 'POST',
        });
        setInfo(`Case submitted. Now awaiting Sales Manager approval.`);
      } else {
        setInfo('Draft saved.');
      }
      // Phase 38 fix: every PATCH replaces cheque rows server-side
      // (with brand-new ids), so we MUST mirror the response back
      // into local state - otherwise the cheque paperclip stays
      // disabled because its ``chequeId`` prop still points at the
      // old (or undefined) id and ``meta`` is stale.
      setMeta(saved);
      setDraft(toDraft(saved));
      // ``router.push`` is a no-op when the URL doesn't change
      // (PATCH on the same case_id), but it's the right thing to
      // do after the initial POST so the URL reflects the new
      // case_id. ``router.refresh`` is kept for any server-rendered
      // shell that might cache fragments of the case page.
      if (!caseId) router.push(`/cases/${id}`);
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
          <SignedFormPanel
            caseId={meta.id}
            status={meta.status}
            onChange={() => setReloadKey((k) => k + 1)}
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
              key={c.id ?? `new-${i}`}
              className="grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] items-end gap-3 rounded-lg border border-[rgb(var(--color-border))] p-3"
            >
              <div className="flex flex-col items-center gap-1">
                <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                  #{i + 1}
                </div>
                <ChequeAttachmentButton
                  caseId={meta?.id ?? null}
                  chequeId={c.id ?? null}
                  disabled={locked}
                  onAutoFill={(ocr) => {
                    if (!ocr.success) return;
                    // Phase 38: cheque-copy OCR auto-fills #/Bank/
                    // Amount/Date only. Bounce reason isn't on the
                    // cheque image - it's read from the case-level
                    // Bank Return Letter attachment.
                    upCheque(i, {
                      ...(ocr.cheque_number
                        ? { cheque_number: ocr.cheque_number }
                        : {}),
                      ...(ocr.bank_id ? { bank_id: ocr.bank_id } : {}),
                      ...(ocr.amount ? { amount: ocr.amount } : {}),
                      ...(ocr.cheque_date ? { cheque_date: ocr.cheque_date } : {}),
                      ...(ocr.cheque_type ? { cheque_type: ocr.cheque_type } : {}),
                    });
                  }}
                />
              </div>
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
                  <BounceReasonPicker
                    value={c.bounce_reason}
                    disabled={locked}
                    onChange={(v) => upCheque(i, { bounce_reason: v })}
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
          {/* Phase 39: attachments are uploadable at every point in
              the lifecycle - a renewed CR Copy or new Computer Card
              may arrive months/years after the case was submitted.
              Removal is only blocked once the case is Closed or
              Rejected (the audit trail must stay intact for finalised
              cases).
          */}
          <CategorizedAttachments
            caseId={meta.id}
            attachments={meta.attachments}
            locked={
              meta.status === 'Closed' ||
              meta.status === 'Rejected' ||
              !canDoAction(caps, ACTION.CASE_CREATE)
            }
            onChange={(atts) => setMeta({ ...meta, attachments: atts })}
          />
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
            id: ch.id,
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

// Phase 38: bounce-reason picker with the common bank-return
// reasons as a dropdown plus a "Custom..." fallback for edge
// cases the list doesn't cover.
const BOUNCE_REASONS = [
  'Insufficient Funds',
  'Account Closed',
  'Stop Payment',
  'Signature Mismatch',
  'Refer to Drawer',
  'Post-Dated',
  'Stale Cheque',
  'Amount in Words / Figures Mismatch',
] as const;

function BounceReasonPicker({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}) {
  const presetMatch = (BOUNCE_REASONS as readonly string[]).includes(value);
  const [custom, setCustom] = useState(!!value && !presetMatch);
  // Track the dropdown selection separately so the user can pick
  // "Custom..." then type something - without it, the select
  // would immediately snap back to "--".
  const selectValue = custom ? '__custom__' : presetMatch ? value : '';
  return (
    <div className="flex flex-1 flex-col gap-1">
      <select
        value={selectValue}
        disabled={disabled}
        onChange={(e) => {
          const v = e.target.value;
          if (v === '__custom__') {
            setCustom(true);
            onChange('');
          } else {
            setCustom(false);
            onChange(v);
          }
        }}
        className={inputCls}
      >
        <option value="">--</option>
        {BOUNCE_REASONS.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
        <option value="__custom__">Custom…</option>
      </select>
      {custom && (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="Type the reason"
          className={inputCls}
        />
      )}
    </div>
  );
}

