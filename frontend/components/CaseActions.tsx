'use client';

import { Check, X, AlertTriangle, Send } from 'lucide-react';
import { useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Action = 'approve' | 'reject' | 'request_clarification' | 'resubmit';

type Props = {
  caseId: number;
  status: string;
  currentStage: string;
  /** Re-fetch the case after a successful transition. */
  onDone: () => void;
};

export function CaseActions({ caseId, status, currentStage, onDone }: Props) {
  const [open, setOpen] = useState<Action | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const isApprovalStage = ![
    'Accountant',
    'Lawyer',
    'Closed',
  ].includes(currentStage);
  const isClarifyState = status === 'Clarification Requested';
  const isFinal = status === 'Approved' || status === 'Rejected';

  if (isFinal) {
    return (
      <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 text-sm text-[rgb(var(--color-muted))]">
        Case is <strong>{status}</strong>. No further approval actions.
        {status === 'Approved' && currentStage === 'Lawyer' && (
          <> Court filing is handled in Phase 4 (coming next).</>
        )}
      </div>
    );
  }

  async function submitAction(a: Action) {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/cases/${caseId}/transition`, {
        method: 'POST',
        body: { action: a, comment },
      });
      setOpen(null);
      setComment('');
      onDone();
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
          {isApprovalStage && (
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
          {isClarifyState && (
            <Btn variant="green" onClick={() => setOpen('resubmit')}>
              <Send className="h-4 w-4" /> Resubmit
            </Btn>
          )}
          {!isApprovalStage && !isClarifyState && (
            <div className="text-xs text-[rgb(var(--color-muted))]">
              No approval action available at this stage.
            </div>
          )}
        </div>
      )}

      {open && (
        <div className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
              {open === 'approve'
                ? 'Approval comment (optional)'
                : open === 'reject'
                  ? 'Rejection reason (required)'
                  : open === 'request_clarification'
                    ? 'What clarification do you need? (required)'
                    : 'Notes (optional)'}
            </span>
            <textarea
              rows={3}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
            />
          </label>
          <div className="flex gap-2">
            <Btn
              variant={open === 'reject' ? 'red' : open === 'request_clarification' ? 'gold' : 'green'}
              onClick={() => submitAction(open)}
              disabled={busy}
            >
              Confirm {labelFor(open)}
            </Btn>
            <Btn variant="ghost" onClick={() => setOpen(null)} disabled={busy}>
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
      return 'Clarification';
    case 'resubmit':
      return 'Resubmit';
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
