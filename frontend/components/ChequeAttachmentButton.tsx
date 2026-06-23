'use client';

import {
  CheckCircle2,
  Eye,
  ListChecks,
  Loader2,
  Paperclip,
  Trash2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { AttachmentViewerModal } from '@/components/AttachmentViewerModal';

/**
 * Phase 36: paperclip icon shown on each cheque row.
 *
 * Clicking it opens a hidden file picker. The selected file is
 * uploaded as a "bank return acknowledgement letter" - the backend
 * OCRs it (Tesseract by default, Vision LLM if configured) and
 * the resulting fields are handed back via ``onAutoFill`` so the
 * parent form can populate the row inline.
 *
 * Until the case has been saved at least once (so it has an id
 * and the cheque rows have ids in the DB), the button is disabled
 * with a tooltip - we can't attach to a cheque that doesn't exist
 * server-side yet.
 */
type OcrFields = {
  success: boolean;
  engine: string;
  cheque_number: string | null;
  bank_id: number | null;
  bank_name: string | null;
  amount: string | null;
  cheque_date: string | null;
  cheque_type: string | null;
  bounce_reason: string | null;
  warnings: string[];
};

type ExistingAttachment = {
  id: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  is_bank_return_letter: boolean;
};

export function ChequeAttachmentButton({
  caseId,
  chequeId,
  disabled,
  onAutoFill,
}: {
  caseId: number | null;
  chequeId: number | null;
  disabled?: boolean;
  onAutoFill: (fields: OcrFields) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showList, setShowList] = useState(false);
  const [existing, setExisting] = useState<ExistingAttachment[]>([]);
  const [view, setView] = useState<ExistingAttachment | null>(null);

  const notReady = !caseId || !chequeId;
  const isDisabled = disabled || notReady || busy;

  // Refresh the per-cheque attachment list whenever the dropdown
  // is opened (we don't poll - the form already re-renders after
  // each upload).
  useEffect(() => {
    if (!showList || !caseId || !chequeId) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await api<ExistingAttachment[]>(
          `/api/v1/cases/${caseId}/cheques/${chequeId}/attachments`,
        );
        if (!cancelled) setExisting(rows);
      } catch (e) {
        if (!cancelled) setErr((e as ApiError).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showList, caseId, chequeId]);

  async function removeOne(id: number) {
    if (!caseId || !chequeId) return;
    if (!confirm('Remove this attachment?')) return;
    try {
      await api(
        `/api/v1/cases/${caseId}/cheques/${chequeId}/attachments/${id}`,
        { method: 'DELETE' },
      );
      setExisting((rows) => rows.filter((r) => r.id !== id));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function upload(file: File) {
    if (!caseId || !chequeId) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('is_bank_return_letter', 'true');
      const token = useAuthStore.getState().accessToken;
      const r = await fetch(
        `${API_BASE}/api/v1/cases/${caseId}/cheques/${chequeId}/attachments`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: fd,
        },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail || `Upload failed (${r.status})`);
      }
      const body = await r.json();
      const ocr: OcrFields = body.ocr;
      onAutoFill(ocr);
      // Append the newly uploaded row so the popover (if open)
      // reflects it without a refetch.
      if (body.attachment) setExisting((rows) => [...rows, body.attachment]);
      if (ocr.success) {
        const filled = [
          ocr.cheque_number && '#',
          ocr.bank_id && 'Bank',
          ocr.amount && 'Amount',
          ocr.cheque_date && 'Date',
          ocr.bounce_reason && 'Reason',
        ]
          .filter(Boolean)
          .join(', ');
        setInfo(`Auto-filled from bank letter: ${filled || '(no fields matched)'}`);
      } else {
        setInfo('Attached. OCR could not read the file - fill the row manually.');
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative inline-flex items-center gap-1">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/jpg,application/pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = '';
        }}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={isDisabled}
        title={
          notReady
            ? 'Save the case first to attach a bank letter'
            : 'Attach a bank return acknowledgement letter (OCR auto-fills the row)'
        }
        className="inline-flex items-center justify-center rounded-md border border-[rgb(var(--color-border))] p-1.5 text-[rgb(var(--color-muted))] hover:bg-pug-gold-500/10 hover:text-pug-gold-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Paperclip className="h-3.5 w-3.5" />
        )}
      </button>
      {!notReady && (
        <button
          type="button"
          onClick={() => setShowList((s) => !s)}
          title="Show attached letters for this cheque"
          className="inline-flex items-center justify-center rounded-md border border-[rgb(var(--color-border))] p-1.5 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
        >
          <ListChecks className="h-3.5 w-3.5" />
        </button>
      )}
      {showList && (
        <div className="absolute left-0 top-full z-20 mt-1 w-80 rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-2 shadow-lg">
          <div className="mb-1 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <span>Cheque Attachments</span>
            <button
              type="button"
              onClick={() => setShowList(false)}
              className="text-[rgb(var(--color-muted))] hover:underline"
            >
              close
            </button>
          </div>
          {existing.length === 0 ? (
            <div className="px-2 py-1 text-[11px] text-[rgb(var(--color-muted))]">
              No letters attached yet.
            </div>
          ) : (
            <ul className="space-y-1">
              {existing.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center gap-1 rounded border border-transparent px-1 py-1 text-[11px] hover:border-[rgb(var(--color-border))]"
                >
                  <span className="min-w-0 flex-1 truncate" title={a.original_filename}>
                    {a.original_filename}
                  </span>
                  <button
                    type="button"
                    onClick={() => setView(a)}
                    className="rounded p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40 hover:text-pug-navy-700"
                    title="View"
                  >
                    <Eye className="h-3 w-3" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeOne(a.id)}
                    className="rounded p-1 text-rose-600 hover:bg-rose-500/10"
                    title="Remove"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <AttachmentViewerModal
        open={view !== null}
        onClose={() => setView(null)}
        viewUrl={
          view && caseId && chequeId
            ? `/api/v1/cases/${caseId}/cheques/${chequeId}/attachments/${view.id}/view`
            : ''
        }
        downloadUrl={
          view && caseId && chequeId
            ? `/api/v1/cases/${caseId}/cheques/${chequeId}/attachments/${view.id}/download`
            : ''
        }
        filename={view?.original_filename ?? ''}
        mimeType={view?.mime_type ?? 'application/octet-stream'}
      />
      {info && (
        <div className="absolute left-0 top-full z-20 mt-1 w-72 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-700 shadow-lg dark:text-emerald-300">
          <CheckCircle2 className="-mt-0.5 mr-1 inline h-3 w-3" />
          {info}
          <button
            type="button"
            onClick={() => setInfo(null)}
            className="ml-2 text-emerald-900/60 hover:text-emerald-900 dark:text-emerald-200/60 dark:hover:text-emerald-200"
          >
            dismiss
          </button>
        </div>
      )}
      {err && (
        <div className="absolute left-0 top-full z-20 mt-1 w-72 rounded-md border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700 shadow-lg dark:text-rose-300">
          {err}
          <button
            type="button"
            onClick={() => setErr(null)}
            className="ml-2 text-rose-900/60 hover:text-rose-900 dark:text-rose-200/60 dark:hover:text-rose-200"
          >
            dismiss
          </button>
        </div>
      )}
    </div>
  );
}
