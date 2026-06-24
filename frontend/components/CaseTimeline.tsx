'use client';

import {
  AlertTriangle,
  ArrowRight,
  Check,
  Circle,
  Eye,
  Gavel,
  Lock,
  MessageSquare,
  Paperclip,
  Send,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { AttachmentViewerModal } from '@/components/AttachmentViewerModal';
import {
  formatBytes,
  type TimelineEntry,
  type TransitionAttachment,
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
      {/* Top flow strip - the stage-by-stage state of the workflow */}
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

      {/* History as a workflow chart - vertical stepper, one card per
          recorded transition. Replaces the previous tabular log. */}
      <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          History
        </div>
        {entries.length === 0 ? (
          <div className="text-sm text-[rgb(var(--color-muted))]">
            No actions recorded yet.
          </div>
        ) : (
          <ol className="relative ml-3 border-l-2 border-dashed border-[rgb(var(--color-border))] pl-6">
            {entries.map((e, idx) => (
              <HistoryCard
                key={e.id}
                entry={e}
                caseId={caseId}
                isLast={idx === entries.length - 1}
              />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function HistoryCard({
  entry,
  caseId,
  isLast,
}: {
  entry: TimelineEntry;
  caseId: number;
  isLast: boolean;
}) {
  const Icon = entryIcon(entry.action_type);
  const dotColor = dotBg(entry.action_type);
  const cardAccent = cardAccentColor(entry.action_type);
  return (
    <li className={`relative ${isLast ? '' : 'pb-5'}`}>
      {/* Connector dot positioned ON the vertical line */}
      <span
        className={`absolute -left-[33px] flex h-7 w-7 items-center justify-center rounded-full border-2 border-[rgb(var(--color-card))] ${dotColor} shadow`}
      >
        <Icon className="h-3.5 w-3.5" />
      </span>

      <div
        className={`rounded-lg border bg-[rgb(var(--color-bg))] p-3 ${cardAccent}`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{labelFor(entry.action_type)}</span>
          <span className="inline-flex items-center gap-1 rounded-md bg-[rgb(var(--color-border))]/40 px-2 py-0.5 font-mono text-[10px]">
            {entry.from_stage} <ArrowRight className="h-3 w-3" /> {entry.to_stage}
          </span>
          <span className="ml-auto text-[10px] text-[rgb(var(--color-muted))]">
            {new Date(entry.created_at).toLocaleString()}
          </span>
        </div>
        <div className="mt-1 text-xs text-[rgb(var(--color-muted))]">
          by <strong>{entry.actor_name || `User #${entry.actor_id}`}</strong>
        </div>
        {entry.comment && (
          <div className="mt-2 whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/30 px-2 py-1.5 text-xs">
            {entry.comment}
          </div>
        )}
        {entry.attachments.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {entry.attachments.map((a) => (
              <li key={a.id}>
                <AttachmentChip caseId={caseId} attachment={a} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

function AttachmentChip({
  caseId,
  attachment,
}: {
  caseId: number;
  attachment: TransitionAttachment;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] px-2 py-1 text-[11px] hover:bg-[rgb(var(--color-border))]/40"
        title="Preview, download or print"
      >
        <Paperclip className="h-3 w-3 text-pug-gold-700 dark:text-pug-gold-400" />
        <span className="font-medium">{attachment.original_filename}</span>
        <span className="text-[10px] text-[rgb(var(--color-muted))]">
          ({formatBytes(attachment.size_bytes)})
        </span>
        <Eye className="h-3 w-3" />
      </button>
      <AttachmentViewerModal
        open={open}
        onClose={() => setOpen(false)}
        viewUrl={`/api/v1/cases/${caseId}/transition-attachments/${attachment.id}/view`}
        downloadUrl={`/api/v1/cases/${caseId}/transition-attachments/${attachment.id}/download`}
        filename={attachment.original_filename}
        mimeType={attachment.mime_type || 'application/octet-stream'}
      />
    </>
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
    case 'lawyer_approve':
      return 'Lawyer Approved';
    case 'court_filed':
      return 'Court Filed';
    case 'closed':
      return 'Closed';
    case 'comment':
      return 'Comment';
    default:
      return a;
  }
}

function dotBg(a: string): string {
  switch (a) {
    case 'approve':
    case 'submit':
    case 'resubmit':
    case 'lawyer_approve':
      return 'bg-emerald-500 text-white';
    case 'reject':
      return 'bg-rose-500 text-white';
    case 'request_clarification':
      return 'bg-pug-gold-500 text-pug-navy-800';
    case 'court_filed':
      return 'bg-pug-navy-600 text-white';
    case 'closed':
      return 'bg-slate-700 text-white';
    default:
      return 'bg-[rgb(var(--color-border))] text-[rgb(var(--color-muted))]';
  }
}

function cardAccentColor(a: string): string {
  switch (a) {
    case 'approve':
    case 'submit':
    case 'resubmit':
    case 'lawyer_approve':
      return 'border-emerald-500/30';
    case 'reject':
      return 'border-rose-500/30';
    case 'request_clarification':
      return 'border-pug-gold-500/40';
    case 'court_filed':
      return 'border-pug-navy-500/40';
    case 'closed':
      return 'border-slate-500/30';
    default:
      return 'border-[rgb(var(--color-border))]';
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
    case 'lawyer_approve':
      return Gavel;
    case 'court_filed':
      return Send;
    case 'closed':
      return Lock;
    default:
      return MessageSquare;
  }
}
