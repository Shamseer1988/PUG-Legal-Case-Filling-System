'use client';

import { Check, Circle, AlertTriangle, Download, MessageSquare, Paperclip, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  downloadTransitionAttachment,
  formatBytes,
  type TimelineEntry,
} from '@/lib/transitionAttachments';

type Stage = {
  key: string;
  stage: string;
  next_stage: string | null;
  sla_hours: number;
};

type Workflow = {
  stages: Stage[];
  accountant_stage: string;
  lawyer_stage: string;
};

type Props = {
  caseId: number;
  currentStage: string;
  status: string;
};

export function CaseTimeline({ caseId, currentStage, status }: Props) {
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [wf, setWf] = useState<Workflow | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [tl, w] = await Promise.all([
          api<TimelineEntry[]>(`/api/v1/cases/${caseId}/timeline`),
          api<Workflow>(`/api/v1/approvals/workflow`),
        ]);
        setEntries(tl);
        setWf(w);
      } catch {
        /* ignore */
      }
    })();
  }, [caseId]);

  const flow: string[] = wf
    ? [wf.accountant_stage, ...wf.stages.map((s) => s.stage), wf.lawyer_stage]
    : [];

  function stateOf(stage: string): 'done' | 'current' | 'pending' | 'rejected' {
    if (status === 'Rejected') {
      const passed = entries.some((e) => e.to_stage === stage && e.action_type === 'approve');
      if (stage === currentStage) return 'rejected';
      return passed ? 'done' : 'pending';
    }
    if (stage === currentStage) return 'current';
    const passed = entries.some((e) => e.to_stage === stage && e.action_type !== 'request_clarification');
    return passed ? 'done' : 'pending';
  }

  return (
    <div className="space-y-4">
      {/* Flow strip */}
      <div className="overflow-x-auto">
        <div className="flex min-w-max items-center gap-2 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-3 shadow-soft">
          {flow.map((stage, i) => {
            const st = stateOf(stage);
            const color =
              st === 'done'
                ? 'bg-emerald-500 text-white border-emerald-600'
                : st === 'current'
                  ? 'bg-pug-gold-500 text-pug-navy-800 border-pug-gold-700 ring-4 ring-pug-gold-500/30'
                  : st === 'rejected'
                    ? 'bg-rose-500 text-white border-rose-600'
                    : 'bg-[rgb(var(--color-border))] text-[rgb(var(--color-muted))] border-[rgb(var(--color-border))]';
            const Icon = st === 'done' ? Check : st === 'rejected' ? X : Circle;
            return (
              <div key={stage} className="flex items-center gap-2">
                <div className="flex flex-col items-center">
                  <div className={`flex h-8 w-8 items-center justify-center rounded-full border ${color}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="mt-1 max-w-[7rem] text-center text-[10px] font-semibold leading-tight">
                    {stage}
                  </div>
                </div>
                {i < flow.length - 1 && (
                  <div className="mx-1 h-px w-8 bg-[rgb(var(--color-border))]" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Entry log */}
      <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <div className="border-b border-[rgb(var(--color-border))] px-4 py-2 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          History
        </div>
        {entries.length === 0 ? (
          <div className="px-4 py-3 text-sm text-[rgb(var(--color-muted))]">
            No actions recorded yet.
          </div>
        ) : (
          <ol className="divide-y divide-[rgb(var(--color-border))]">
            {entries.map((e) => {
              const Icon = entryIcon(e.action_type);
              return (
                <li key={e.id} className="flex gap-3 px-4 py-3 text-sm">
                  <div
                    className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${entryColor(
                      e.action_type,
                    )}`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-semibold">{labelFor(e.action_type)}</span>
                      <span className="text-xs text-[rgb(var(--color-muted))]">
                        {e.from_stage} {arrowFor(e.action_type)} {e.to_stage} &middot;{' '}
                        {e.actor_name || `User #${e.actor_id}`} &middot;{' '}
                        {new Date(e.created_at).toLocaleString()}
                      </span>
                    </div>
                    {e.comment && (
                      <div className="mt-1 whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/30 px-2 py-1 text-xs">
                        {e.comment}
                      </div>
                    )}
                    {e.attachments.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {e.attachments.map((a) => (
                          <li key={a.id}>
                            <AttachmentLink caseId={caseId} attachment={a} />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}

function AttachmentLink({
  caseId,
  attachment,
}: {
  caseId: number;
  attachment: import('@/lib/transitionAttachments').TransitionAttachment;
}) {
  const [busy, setBusy] = useState(false);
  async function open() {
    setBusy(true);
    try {
      const { url } = await downloadTransitionAttachment(caseId, attachment.id);
      // Trigger download via temp anchor so the browser uses the
      // original filename instead of the blob: URL hash.
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment.original_filename;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Revoke after a tick so the navigation has a chance to start.
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      onClick={open}
      disabled={busy}
      className="inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] px-2 py-1 text-[11px] hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-50"
    >
      <Paperclip className="h-3 w-3 text-pug-gold-700 dark:text-pug-gold-400" />
      <span className="font-medium">{attachment.original_filename}</span>
      <span className="text-[10px] text-[rgb(var(--color-muted))]">
        ({formatBytes(attachment.size_bytes)})
      </span>
      <Download className="h-3 w-3" />
    </button>
  );
}

function labelFor(a: string): string {
  switch (a) {
    case 'submit':
      return 'Submitted';
    case 'approve':
      return 'Approved';
    case 'reject':
      return 'Rejected';
    case 'request_clarification':
      return 'Requested Clarification';
    case 'resubmit':
      return 'Resubmitted';
    case 'comment':
      return 'Comment';
    default:
      return a;
  }
}

function arrowFor(a: string): string {
  if (a === 'reject') return 'X';
  return '->';
}

function entryColor(a: string): string {
  switch (a) {
    case 'approve':
    case 'submit':
    case 'resubmit':
      return 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300';
    case 'reject':
      return 'bg-rose-500/20 text-rose-700 dark:text-rose-300';
    case 'request_clarification':
      return 'bg-pug-gold-500/20 text-pug-gold-700 dark:text-pug-gold-300';
    default:
      return 'bg-slate-500/20 text-slate-700 dark:text-slate-300';
  }
}

function entryIcon(a: string) {
  switch (a) {
    case 'approve':
    case 'submit':
    case 'resubmit':
      return Check;
    case 'reject':
      return X;
    case 'request_clarification':
      return AlertTriangle;
    default:
      return MessageSquare;
  }
}
