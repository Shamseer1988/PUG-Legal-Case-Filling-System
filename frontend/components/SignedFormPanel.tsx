'use client';

import { Eye, FileSignature, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, ApiError, API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { ACTION, canDoAction, useCapabilitiesStore } from '@/lib/capabilities';
import { formatBytes } from '@/lib/transitionAttachments';
import { AttachmentViewerModal } from '@/components/AttachmentViewerModal';

type SignedFormAttachment = {
  id: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  category: string;
  uploaded_by_id: number;
  created_at: string;
};

type Props = {
  caseId: number;
  /** Hide entirely on Draft cases — there's no form to sign yet. */
  status: string;
  onChange: () => void;
};

/** Signed Case Form panel.
 *
 * - The "Signed Case Form" is the PDF the FM or Lawyer uploads
 *   after signing the printed application.
 * - Upload / replace / remove are gated on ACTION.CASE_SIGNED_FORM_UPLOAD
 *   (granted to Finance Manager, Lawyer and Admin by the Phase 14
 *   capability matrix).
 * - Anyone with read access to the case sees the download chip
 *   once a signed copy exists.
 */
export function SignedFormPanel({ caseId, status, onChange }: Props) {
  const caps = useCapabilitiesStore((s) => s.caps);
  const token = useAuthStore((s) => s.accessToken);
  const canUpload = canDoAction(caps, ACTION.CASE_SIGNED_FORM_UPLOAD);
  const [attachment, setAttachment] = useState<SignedFormAttachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function load() {
    try {
      const a = await api<SignedFormAttachment | null>(
        `/api/v1/cases/${caseId}/signed-form`,
      );
      setAttachment(a);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  // Nothing to sign while the case is still being drafted.
  if (status === 'Draft') return null;

  // Read-only users with nothing on file: don't clutter the page.
  if (!attachment && !canUpload) return null;

  async function upload(file: File) {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(`${API_BASE}/api/v1/cases/${caseId}/signed-form`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: fd,
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail || `Upload failed (${r.status})`);
      }
      const att: SignedFormAttachment = await r.json();
      setAttachment(att);
      setInfo('Signed form saved.');
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function remove() {
    if (!attachment) return;
    if (!confirm('Remove the signed form?')) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      await api(`/api/v1/cases/${caseId}/signed-form`, { method: 'DELETE' });
      setAttachment(null);
      setInfo('Signed form removed.');
      onChange();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  function openViewer() {
    if (attachment) setViewOpen(true);
  }

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <FileSignature className="h-4 w-4 text-pug-gold-700 dark:text-pug-gold-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Signed Case Form
        </h2>
        {attachment && (
          <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            On file
          </span>
        )}
      </div>

      <p className="mb-3 text-xs text-[rgb(var(--color-muted))]">
        Upload the signed copy of the printed application form. Finance
        Manager or Lawyer typically attaches this after collecting
        wet-ink signatures.
      </p>

      {err && (
        <div className="mb-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="mb-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          {info}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {attachment ? (
          <button
            type="button"
            onClick={openViewer}
            className="inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
            title="Preview, download or print"
          >
            <Eye className="h-3.5 w-3.5" />
            {attachment.original_filename}
            <span className="text-[10px] text-[rgb(var(--color-muted))]">
              ({formatBytes(attachment.size_bytes)})
            </span>
          </button>
        ) : (
          <span className="text-xs text-[rgb(var(--color-muted))]">
            No signed form uploaded yet.
          </span>
        )}

        {canUpload && (
          <>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              className={`inline-flex items-center gap-2 rounded-md px-2 py-1 text-xs font-semibold disabled:opacity-50 ${
                attachment
                  ? 'bg-pug-navy-700 text-white hover:bg-pug-navy-600'
                  : 'bg-pug-gold-500 text-pug-navy-800 hover:bg-pug-gold-400'
              }`}
            >
              <Upload className="h-3.5 w-3.5" />
              {attachment ? 'Replace' : 'Upload Signed Form'}
            </button>
            {attachment && (
              <button
                type="button"
                onClick={remove}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-md border border-rose-500/40 px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10 disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" /> Remove
              </button>
            )}
          </>
        )}

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
          }}
        />
      </div>
      <AttachmentViewerModal
        open={viewOpen}
        onClose={() => setViewOpen(false)}
        viewUrl={
          attachment
            ? `/api/v1/cases/${caseId}/attachments/${attachment.id}/view`
            : ''
        }
        downloadUrl={
          attachment
            ? `/api/v1/cases/${caseId}/attachments/${attachment.id}/download`
            : ''
        }
        filename={attachment?.original_filename ?? ''}
        mimeType={attachment?.mime_type ?? 'application/octet-stream'}
      />
    </section>
  );
}
