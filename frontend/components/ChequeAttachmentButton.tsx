'use client';

import { CheckCircle2, Loader2, Paperclip } from 'lucide-react';
import { useRef, useState } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

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

  const notReady = !caseId || !chequeId;
  const isDisabled = disabled || notReady || busy;

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
    <div className="relative inline-block">
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
