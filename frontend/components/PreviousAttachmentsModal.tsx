'use client';

import { Download, Paperclip, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  downloadTransitionAttachment,
  formatBytes,
  type TimelineEntry,
} from '@/lib/transitionAttachments';

type Props = { caseId: number };

/** One-shot modal that surfaces attachments left by the previous
 *  reviewer so the current reviewer doesn't miss the evidence.
 *
 *  Behaviour:
 *  - Fires once per (case, transition_id) tuple per browser session.
 *  - Loads the timeline, picks the most recent transition that has
 *    attachments, and shows the file list with download buttons.
 *  - Dismisses for the rest of the session via sessionStorage so
 *    re-renders / route changes don't re-pop it.
 */
export function PreviousAttachmentsModal({ caseId }: Props) {
  const [entry, setEntry] = useState<TimelineEntry | null>(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const tl = await api<TimelineEntry[]>(`/api/v1/cases/${caseId}/timeline`);
        if (cancelled || tl.length === 0) return;
        const latestWithFiles = [...tl]
          .reverse()
          .find((e) => e.attachments && e.attachments.length > 0);
        if (!latestWithFiles) return;
        const key = `pug-prev-att-seen:${caseId}:${latestWithFiles.id}`;
        if (sessionStorage.getItem(key)) return;
        sessionStorage.setItem(key, '1');
        setEntry(latestWithFiles);
        setShow(true);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  if (!show || !entry) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            <Paperclip className="h-4 w-4" /> Attachments from previous reviewer
          </h3>
          <button
            onClick={() => setShow(false)}
            className="rounded-md p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="px-5 py-4">
          <p className="mb-3 text-xs text-[rgb(var(--color-muted))]">
            <strong>{entry.actor_name || `User #${entry.actor_id}`}</strong>{' '}
            attached {entry.attachments.length} file
            {entry.attachments.length === 1 ? '' : 's'} when moving the case from{' '}
            <strong>{entry.from_stage}</strong> to <strong>{entry.to_stage}</strong>.
            Review them before you act on this case.
          </p>
          {entry.comment && (
            <div className="mb-3 whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/30 px-3 py-2 text-xs">
              <span className="block text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Comment
              </span>
              {entry.comment}
            </div>
          )}
          <ul className="space-y-2">
            {entry.attachments.map((a) => (
              <AttachmentRow key={a.id} caseId={caseId} att={a} />
            ))}
          </ul>
        </div>
        <div className="flex justify-end gap-2 border-t border-[rgb(var(--color-border))] px-5 py-3">
          <button
            onClick={() => setShow(false)}
            className="rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}

function AttachmentRow({
  caseId,
  att,
}: {
  caseId: number;
  att: import('@/lib/transitionAttachments').TransitionAttachment;
}) {
  const [busy, setBusy] = useState(false);
  async function download() {
    setBusy(true);
    try {
      const { url } = await downloadTransitionAttachment(caseId, att.id);
      const a = document.createElement('a');
      a.href = url;
      a.download = att.original_filename;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="flex items-center justify-between gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm">
      <span className="truncate">
        <span className="font-medium">{att.original_filename}</span>{' '}
        <span className="text-[11px] text-[rgb(var(--color-muted))]">
          ({formatBytes(att.size_bytes)})
        </span>
      </span>
      <button
        onClick={download}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-md bg-pug-gold-500 px-2 py-1 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
      >
        <Download className="h-3.5 w-3.5" /> Download
      </button>
    </li>
  );
}
