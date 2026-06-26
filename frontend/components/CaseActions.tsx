'use client';

import { Check, X, AlertTriangle, Gavel, Paperclip, Send, Upload, Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { ACTION, canDoAction, useCapabilitiesStore } from '@/lib/capabilities';
import {
  deletePendingTransitionAttachment,
  formatBytes,
  uploadTransitionAttachment,
  type TransitionAttachment,
} from '@/lib/transitionAttachments';

type Action = 'approve' | 'reject' | 'request_clarification' | 'resubmit' | 'lawyer_approve';

// Full approval stage order (matches the backend WORKFLOW_STAGES list).
const APPROVAL_STAGE_ORDER = [
  'Sales Manager',
  'Division Manager',
  'Audit',
  'Finance Manager',
  'Executive Director',
  'Chairman / MD',
];

// Permission required to answer a clarification directed at each stage.
const CLARIFY_STAGE_PERM: Record<string, string> = {
  Accountant: ACTION.CASE_CREATE,
  'Sales Manager': ACTION.CASE_APPROVE_SALES_MGR,
  'Division Manager': ACTION.CASE_APPROVE_DIV_MGR,
  Audit: ACTION.CASE_APPROVE_AUDIT,
  'Finance Manager': ACTION.CASE_APPROVE_FM,
  'Executive Director': ACTION.CASE_APPROVE_ED,
  'Chairman / MD': ACTION.CASE_APPROVE_FINAL,
};

type Props = {
  caseId: number;
  status: string;
  currentStage: string;
  /** From case.clarify_from_stage — which stage was asked for clarification. */
  clarifyFromStage: string | null;
  /** Re-fetch the case after a successful transition. */
  onDone: () => void;
};

export function CaseActions({
  caseId,
  status,
  currentStage,
  clarifyFromStage,
  onDone,
}: Props) {
  const [open, setOpen] = useState<Action | null>(null);
  const [comment, setComment] = useState('');
  const [clarifyTarget, setClarifyTarget] = useState('Accountant');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState<TransitionAttachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const router = useRouter();

  const caps = useCapabilitiesStore((s) => s.caps);
  const isApprovalStage = !['Accountant', 'Lawyer', 'Closed'].includes(currentStage);
  const isClarifyState = status === 'Clarification Requested';

  // Reset clarify target when the modal opens.
  useEffect(() => {
    if (open === 'request_clarification') {
      setClarifyTarget('Accountant');
    }
  }, [open]);

  // Stages the current approver can direct a clarification at:
  // all stages below the current one (by index) + always Accountant.
  const currentIdx = APPROVAL_STAGE_ORDER.indexOf(currentStage);
  const clarifyTargets = [
    { stage: 'Accountant', label: 'Accountant (Case Creator)' },
    ...APPROVAL_STAGE_ORDER.slice(0, currentIdx).map((s) => ({ stage: s, label: s })),
  ];

  // Lawyer Approval is only offered once the case is Filed at Lawyer stage.
  const showLawyerApprove =
    currentStage === 'Lawyer' &&
    status === 'Filed' &&
    canDoAction(caps, ACTION.CASE_LAWYER_APPROVE);

  const STAGE_ACTION: Record<string, string> = {
    'Sales Manager': ACTION.CASE_APPROVE_SALES_MGR,
    'Division Manager': ACTION.CASE_APPROVE_DIV_MGR,
    Audit: ACTION.CASE_APPROVE_AUDIT,
    'Finance Manager': ACTION.CASE_APPROVE_FM,
    'Executive Director': ACTION.CASE_APPROVE_ED,
    'Chairman / MD': ACTION.CASE_APPROVE_FINAL,
  };

  // Approve / Reject / Request Clarification only shown at approval stages
  // when NOT in clarification state (prevents double-action during pendingclarification).
  const canApproveCurrentStage =
    isApprovalStage && !isClarifyState && canDoAction(caps, STAGE_ACTION[currentStage] ?? '');

  // Resubmit is available when the clarification is directed at the current user's role.
  const effectiveClarifyStage = clarifyFromStage || 'Accountant';
  const canResubmit =
    isClarifyState &&
    canDoAction(caps, CLARIFY_STAGE_PERM[effectiveClarifyStage] ?? ACTION.CASE_CREATE);

  const isFinal = status === 'Rejected' || status === 'Closed';

  if (isFinal) {
    return (
      <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 text-sm text-[rgb(var(--color-muted))]">
        Case is <strong>{status}</strong>. No further approval actions.
      </div>
    );
  }

  async function onPickFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setErr(null);
    setBusy(true);
    try {
      const uploaded: TransitionAttachment[] = [];
      for (const f of Array.from(files)) {
        uploaded.push(await uploadTransitionAttachment(caseId, f));
      }
      setPending((p) => [...p, ...uploaded]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function removePending(id: number) {
    try {
      await deletePendingTransitionAttachment(caseId, id);
      setPending((p) => p.filter((x) => x.id !== id));
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  function cancel() {
    pending.forEach((a) => {
      void deletePendingTransitionAttachment(caseId, a.id).catch(() => undefined);
    });
    setPending([]);
    setOpen(null);
    setComment('');
    setClarifyTarget('Accountant');
    setErr(null);
  }

  async function submitAction(a: Action) {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/cases/${caseId}/transition`, {
        method: 'POST',
        body: {
          action: a,
          comment,
          attachment_ids: pending.map((p) => p.id),
          ...(a === 'request_clarification' ? { clarify_from_stage: clarifyTarget } : {}),
        },
      });
      setOpen(null);
      setComment('');
      setClarifyTarget('Accountant');
      setPending([]);
      onDone();
      // Force the App Router to re-fetch the case page's server data
      // so the stage/status pills update from authoritative state,
      // not the local optimistic reload-key bump in the parent. The
      // reload-key path is kept as a belt-and-braces refresh of any
      // client-side data layer the parent might also be using.
      router.refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Actions at {currentStage}
        </h3>
        <span className="text-xs text-[rgb(var(--color-muted))]">
          Status: <strong>{status}</strong>
        </span>
      </div>

      {err && (
        <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {!open && (
        <div className="flex flex-wrap gap-2">
          {canApproveCurrentStage && (
            <>
              <Btn variant="green" onClick={() => setOpen('approve')}>
                <Check className="h-4 w-4" /> Approve
              </Btn>
              <Btn variant="gold" onClick={() => setOpen('request_clarification')}>
                <AlertTriangle className="h-4 w-4" /> Request Clarification
              </Btn>
              <Btn variant="red" onClick={() => setOpen('reject')}>
                <X className="h-4 w-4" /> Reject
              </Btn>
            </>
          )}
          {canResubmit && (
            <Btn variant="green" onClick={() => setOpen('resubmit')}>
              <Send className="h-4 w-4" /> Answer &amp; Resubmit
            </Btn>
          )}
          {showLawyerApprove && (
            <Btn variant="green" onClick={() => setOpen('lawyer_approve')}>
              <Gavel className="h-4 w-4" /> Approve (Lawyer)
            </Btn>
          )}
          {!canApproveCurrentStage && !canResubmit && !showLawyerApprove && (
            <div className="text-xs text-[rgb(var(--color-muted))]">
              {isClarifyState
                ? `Awaiting clarification from ${effectiveClarifyStage}.`
                : isApprovalStage
                  ? `Awaiting ${currentStage} action. You are not authorised to act at this stage.`
                  : 'No approval action available at this stage.'}
            </div>
          )}
        </div>
      )}

      {open && (
        <div className="space-y-3">
          {/* Clarification target picker */}
          {open === 'request_clarification' && clarifyTargets.length > 1 && (
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Request clarification from
              </span>
              <select
                value={clarifyTarget}
                onChange={(e) => setClarifyTarget(e.target.value)}
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
              >
                {clarifyTargets.map((t) => (
                  <option key={t.stage} value={t.stage}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
              {open === 'approve'
                ? 'Approval comment (optional)'
                : open === 'reject'
                  ? 'Rejection reason (required)'
                  : open === 'request_clarification'
                    ? 'What clarification do you need? (required)'
                    : open === 'lawyer_approve'
                      ? 'Lawyer approval note (optional)'
                      : 'Notes (optional)'}
            </span>
            <textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
            />
          </label>

          <div className="rounded-md border border-dashed border-[rgb(var(--color-border))] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                <Paperclip className="h-3.5 w-3.5" /> Attachments (optional)
              </span>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={busy}
                className="inline-flex items-center gap-1 rounded-md bg-pug-navy-700 px-2 py-1 text-xs font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
              >
                <Upload className="h-3.5 w-3.5" /> Add file
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => onPickFiles(e.target.files)}
              />
            </div>
            {pending.length === 0 ? (
              <div className="text-[11px] text-[rgb(var(--color-muted))]">
                The next reviewer will see any files you attach here before they act.
              </div>
            ) : (
              <ul className="space-y-1">
                {pending.map((a) => (
                  <li
                    key={a.id}
                    className="flex items-center justify-between gap-2 rounded bg-[rgb(var(--color-border))]/30 px-2 py-1 text-xs"
                  >
                    <span className="truncate">
                      {a.original_filename}{' '}
                      <span className="text-[10px] text-[rgb(var(--color-muted))]">
                        ({formatBytes(a.size_bytes)})
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={() => removePending(a.id)}
                      className="text-rose-600 hover:text-rose-500"
                      title="Remove"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex gap-2">
            <Btn
              variant={open === 'reject' ? 'red' : open === 'request_clarification' ? 'gold' : 'green'}
              onClick={() => submitAction(open)}
              disabled={busy}
            >
              Confirm {labelFor(open)}
            </Btn>
            <Btn variant="ghost" onClick={cancel} disabled={busy}>
              Cancel
            </Btn>
          </div>
        </div>
      )}
    </div>
  );
}

function labelFor(a: Action): string {
  switch (a) {
    case 'approve':
      return 'Approval';
    case 'reject':
      return 'Rejection';
    case 'request_clarification':
      return 'Clarification Request';
    case 'resubmit':
      return 'Resubmit';
    case 'lawyer_approve':
      return 'Lawyer Approval';
  }
}

function Btn({
  variant,
  children,
  ...rest
}: {
  variant: 'green' | 'red' | 'gold' | 'ghost';
  children: React.ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls = {
    green: 'bg-emerald-600 hover:bg-emerald-500 text-white',
    red: 'bg-rose-600 hover:bg-rose-500 text-white',
    gold: 'bg-pug-gold-500 hover:bg-pug-gold-400 text-pug-navy-800',
    ghost:
      'border border-[rgb(var(--color-border))] hover:bg-[rgb(var(--color-border))]/40 text-[rgb(var(--color-fg))]',
  }[variant];
  return (
    <button
      {...rest}
      className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-50 ${cls}`}
    >
      {children}
    </button>
  );
}
