'use client';

import { Eye, Gavel, Paperclip, Save, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, API_BASE, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { ACTION, canDoAction, useCapabilitiesStore } from '@/lib/capabilities';
import { formatBytes } from '@/lib/transitionAttachments';
import { AttachmentViewerModal } from '@/components/AttachmentViewerModal';

type Filing = {
  id: number;
  case_id: number;
  police_case_no: string;
  court_case_no: string;
  filed_court: string;
  filed_date: string | null;
  notes: string;
  filed_by_name: string;
  created_at: string;
  acknowledgment_attachment_id: number | null;
  acknowledgment_attachment_filename: string;
  acknowledgment_attachment_size: number;
  acknowledgment_attachment_mime: string;
};

type Props = {
  caseId: number;
  status: string;
  onChange: () => void;
};

export function CourtFilingPanel({ caseId, status, onChange }: Props) {
  const caps = useCapabilitiesStore((s) => s.caps);
  const token = useAuthStore((s) => s.accessToken);
  const canFile = canDoAction(caps, ACTION.CASE_FILE);
  const [filing, setFiling] = useState<Filing | null>(null);
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ackBusy, setAckBusy] = useState(false);
  const [viewOpen, setViewOpen] = useState(false);
  const ackInputRef = useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = useState({
    police_case_no: '',
    court_case_no: '',
    filed_court: '',
    filed_date: '',
    notes: '',
  });

  async function load() {
    try {
      const data = await api<Filing | null>(`/api/v1/cases/${caseId}/court-filing`);
      setFiling(data);
      if (data) {
        setDraft({
          police_case_no: data.police_case_no,
          court_case_no: data.court_case_no,
          filed_court: data.filed_court,
          filed_date: data.filed_date ?? '',
          notes: data.notes,
        });
      }
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const blocked =
    status !== 'Approved' && status !== 'Filed' && status !== 'Lawyer Approved';

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const payload = { ...draft, filed_date: draft.filed_date || null };
      if (filing) {
        await api(`/api/v1/cases/${caseId}/court-filing`, { method: 'PATCH', body: payload });
      } else {
        await api(`/api/v1/cases/${caseId}/court-filing`, { method: 'POST', body: payload });
      }
      setEdit(false);
      await load();
      onChange();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadAcknowledgement(file: File) {
    if (!filing) return;
    setAckBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(
        `${API_BASE}/api/v1/cases/${caseId}/court-filing/attachment`,
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
      const next: Filing = await r.json();
      setFiling(next);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setAckBusy(false);
      if (ackInputRef.current) ackInputRef.current.value = '';
    }
  }

  async function removeAcknowledgement() {
    if (!filing?.acknowledgment_attachment_id) return;
    if (!confirm('Remove the acknowledgement file?')) return;
    setAckBusy(true);
    setErr(null);
    try {
      const next = await api<Filing>(
        `/api/v1/cases/${caseId}/court-filing/attachment`,
        { method: 'DELETE' },
      );
      setFiling(next);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setAckBusy(false);
    }
  }

  // Acknowledgement preview/download/print are handled by the
  // AttachmentViewerModal mounted at the end of this component.

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <Gavel className="h-4 w-4 text-pug-gold-700 dark:text-pug-gold-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Court Filing
        </h2>
        {filing && (
          <span className="ml-2 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
            Filed
          </span>
        )}
        {!edit && canFile && !blocked && (
          <button
            onClick={() => setEdit(true)}
            className="ml-auto rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-xs font-semibold hover:bg-[rgb(var(--color-border))]/40"
          >
            {filing ? 'Edit' : 'Record Filing'}
          </button>
        )}
      </div>

      {blocked && (
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Available after Chairman / MD approval.
        </div>
      )}

      {err && (
        <div className="mb-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {!edit && filing && (
        <>
          <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
            <Pair k="Police Case No." v={filing.police_case_no || '-'} />
            <Pair k="Court Case No." v={filing.court_case_no || '-'} />
            <Pair k="Filed Court" v={filing.filed_court || '-'} />
            <Pair k="Filed Date" v={filing.filed_date ?? '-'} />
            <Pair k="Filed By" v={filing.filed_by_name} />
            <Pair k="Recorded At" v={new Date(filing.created_at).toLocaleString()} />
            {filing.notes && (
              <div className="md:col-span-2">
                <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">Notes</div>
                <div className="whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/20 px-3 py-2 text-sm">
                  {filing.notes}
                </div>
              </div>
            )}
          </dl>

          {/* Acknowledgement attachment - now lives on the panel
              itself so the tip text "Tip: upload the govt
              acknowledgement..." actually matches reality. */}
          {canFile && !blocked && (
            <div className="mt-4 rounded-md border border-dashed border-[rgb(var(--color-border))] p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                <Paperclip className="h-3.5 w-3.5" /> Government Acknowledgement
              </div>
              {filing.acknowledgment_attachment_id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setViewOpen(true)}
                    className="inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                    title="Preview, download or print"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    {filing.acknowledgment_attachment_filename || 'Open'}
                    <span className="text-[10px] text-[rgb(var(--color-muted))]">
                      ({formatBytes(filing.acknowledgment_attachment_size)})
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => ackInputRef.current?.click()}
                    disabled={ackBusy}
                    className="inline-flex items-center gap-2 rounded-md bg-pug-navy-700 px-2 py-1 text-xs font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
                  >
                    <Upload className="h-3.5 w-3.5" /> Replace
                  </button>
                  <button
                    type="button"
                    onClick={removeAcknowledgement}
                    disabled={ackBusy}
                    className="inline-flex items-center gap-2 rounded-md border border-rose-500/40 px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10 disabled:opacity-50"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Remove
                  </button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-[rgb(var(--color-muted))]">
                    No acknowledgement uploaded yet.
                  </span>
                  <button
                    type="button"
                    onClick={() => ackInputRef.current?.click()}
                    disabled={ackBusy}
                    className="inline-flex items-center gap-2 rounded-md bg-pug-gold-500 px-2 py-1 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
                  >
                    <Upload className="h-3.5 w-3.5" /> Upload Acknowledgement
                  </button>
                </div>
              )}
              <input
                ref={ackInputRef}
                type="file"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadAcknowledgement(f);
                }}
              />
            </div>
          )}
        </>
      )}

      {!edit && !filing && !blocked && (
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Click <strong>Record Filing</strong> to enter Police / Court case numbers.
          You can attach the government acknowledgement immediately after.
        </div>
      )}

      {edit && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Field label="Police Case No.">
              <input
                value={draft.police_case_no}
                onChange={(e) => setDraft({ ...draft, police_case_no: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label="Court Case No.">
              <input
                value={draft.court_case_no}
                onChange={(e) => setDraft({ ...draft, court_case_no: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label="Filed Court">
              <input
                value={draft.filed_court}
                onChange={(e) => setDraft({ ...draft, filed_court: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label="Filed Date">
              <input
                type="date"
                value={draft.filed_date}
                onChange={(e) => setDraft({ ...draft, filed_date: e.target.value })}
                className={inputCls}
              />
            </Field>
          </div>
          <Field label="Notes">
            <textarea
              rows={3}
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              className={inputCls}
            />
          </Field>
          <div className="flex gap-2">
            <button
              onClick={save}
              disabled={busy}
              className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> Save
            </button>
            <button
              onClick={() => setEdit(false)}
              className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              Cancel
            </button>
          </div>
          <div className="text-[10px] text-[rgb(var(--color-muted))]">
            Tip: save first, then upload the government acknowledgement
            using the field that appears next to the filing details.
          </div>
        </div>
      )}
      <AttachmentViewerModal
        open={viewOpen}
        onClose={() => setViewOpen(false)}
        viewUrl={
          filing?.acknowledgment_attachment_id
            ? `/api/v1/cases/${caseId}/attachments/${filing.acknowledgment_attachment_id}/view`
            : ''
        }
        downloadUrl={
          filing?.acknowledgment_attachment_id
            ? `/api/v1/cases/${caseId}/attachments/${filing.acknowledgment_attachment_id}/download`
            : ''
        }
        filename={filing?.acknowledgment_attachment_filename ?? 'acknowledgement'}
        mimeType={filing?.acknowledgment_attachment_mime ?? 'application/octet-stream'}
      />
    </section>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}

function Pair({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">{k}</div>
      <div className="text-sm">{v}</div>
    </div>
  );
}
