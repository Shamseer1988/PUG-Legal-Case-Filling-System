'use client';

import { CheckSquare, Download, Eye, Paperclip, Square, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { AttachmentViewerModal } from '@/components/AttachmentViewerModal';

/**
 * Phase 36: 7 fixed categories rendered as tiles. The checkbox
 * inside each tile is read-only - it ticks as soon as at least one
 * file in that category is on file. Each tile has an "Attach Files"
 * button, and lists the files with View / Download / Delete actions.
 */

export type AttachmentRow = {
  id: number;
  original_filename: string;
  size_bytes: number;
  mime_type: string;
  category: string;
};

export const CASE_ATTACHMENT_CATEGORIES = [
  'Credit Application',
  'CR Copy',
  'Computer Card',
  'Partners ID',
  'Shop Address',
  'Invoices',
  'Other Docs',
] as const;

type Category = (typeof CASE_ATTACHMENT_CATEGORIES)[number];

function bucketFor(raw: string): Category {
  if ((CASE_ATTACHMENT_CATEGORIES as readonly string[]).includes(raw)) {
    return raw as Category;
  }
  // Legacy "Supporting Document" + anything else falls under Other.
  return 'Other Docs';
}

export function CategorizedAttachments({
  caseId,
  attachments,
  locked,
  onChange,
}: {
  caseId: number;
  attachments: AttachmentRow[];
  locked: boolean;
  onChange: (atts: AttachmentRow[]) => void;
}) {
  const [busyCat, setBusyCat] = useState<Category | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<AttachmentRow | null>(null);

  const grouped = useMemo(() => {
    const out: Record<Category, AttachmentRow[]> = {
      'Credit Application': [],
      'CR Copy': [],
      'Computer Card': [],
      'Partners ID': [],
      'Shop Address': [],
      'Invoices': [],
      'Other Docs': [],
    };
    for (const a of attachments) {
      out[bucketFor(a.category)].push(a);
    }
    return out;
  }, [attachments]);

  async function upload(cat: Category, files: FileList | null) {
    if (!files) return;
    setBusyCat(cat);
    setErr(null);
    try {
      const updated = [...attachments];
      for (const f of Array.from(files)) {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('category', cat);
        const token = useAuthStore.getState().accessToken;
        const r = await fetch(`${API_BASE}/api/v1/cases/${caseId}/attachments`, {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: fd,
        });
        if (!r.ok) {
          throw new Error((await r.json()).detail || 'Upload failed');
        }
        updated.push(await r.json());
      }
      onChange(updated);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyCat(null);
    }
  }

  async function remove(id: number) {
    if (!confirm('Remove this attachment?')) return;
    try {
      await api(`/api/v1/cases/${caseId}/attachments/${id}`, { method: 'DELETE' });
      onChange(attachments.filter((a) => a.id !== id));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function downloadZip() {
    try {
      const token = useAuthStore.getState().accessToken;
      const r = await fetch(
        `${API_BASE}/api/v1/cases/${caseId}/attachments.zip`,
        { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
      );
      if (!r.ok) throw new Error(`ZIP failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `case-${caseId}-attachments.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function directDownload(att: AttachmentRow) {
    try {
      const token = useAuthStore.getState().accessToken;
      const r = await fetch(
        `${API_BASE}/api/v1/cases/${caseId}/attachments/${att.id}/download`,
        { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
      );
      if (!r.ok) throw new Error(`Download failed (${r.status})`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = att.original_filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Files are stored under <code>/storage/cases/&lt;case_no&gt;/</code> and
          travel with the case forever. Tap a row to preview, or download
          everything (including cheque attachments) as one ZIP.
        </p>
        <button
          type="button"
          onClick={downloadZip}
          disabled={attachments.length === 0}
          className="inline-flex items-center gap-2 rounded-md border border-pug-gold-500/40 bg-pug-gold-500/10 px-3 py-1.5 text-xs font-semibold text-pug-gold-700 hover:bg-pug-gold-500/20 disabled:opacity-50 dark:text-pug-gold-300"
        >
          <Download className="h-4 w-4" /> Download All As ZIP
        </button>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {CASE_ATTACHMENT_CATEGORIES.map((cat) => {
          const rows = grouped[cat];
          const hasFiles = rows.length > 0;
          return (
            <div
              key={cat}
              className="rounded-lg border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-3"
            >
              <div className="mb-2 flex items-center gap-2">
                {hasFiles ? (
                  <CheckSquare className="h-4 w-4 text-emerald-600" />
                ) : (
                  <Square className="h-4 w-4 text-[rgb(var(--color-muted))]" />
                )}
                <div className="text-sm font-semibold uppercase tracking-wider">
                  {cat}
                </div>
                <div className="ml-auto text-[10px] text-[rgb(var(--color-muted))]">
                  {rows.length} file{rows.length === 1 ? '' : 's'}
                </div>
              </div>

              {!locked && (
                <label className="mb-2 inline-flex cursor-pointer items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40">
                  <Paperclip className="h-3.5 w-3.5" />
                  {busyCat === cat ? 'Uploading…' : 'Attach Files'}
                  <input
                    type="file"
                    multiple
                    disabled={busyCat === cat}
                    onChange={(e) => {
                      upload(cat, e.target.files);
                      e.target.value = '';
                    }}
                    className="hidden"
                  />
                </label>
              )}

              {rows.length === 0 ? (
                <div className="text-[11px] text-[rgb(var(--color-muted))]">
                  No attachments yet.
                </div>
              ) : (
                <ul className="space-y-1">
                  {rows.map((a) => (
                    <li
                      key={a.id}
                      className="group flex items-center gap-2 rounded border border-transparent px-1 py-1 text-xs hover:border-[rgb(var(--color-border))]"
                    >
                      <button
                        type="button"
                        onClick={() => setView(a)}
                        className="min-w-0 flex-1 truncate text-left hover:underline"
                        title="Preview"
                      >
                        {a.original_filename}
                      </button>
                      <span className="shrink-0 text-[10px] text-[rgb(var(--color-muted))]">
                        {(a.size_bytes / 1024).toFixed(1)} KB
                      </span>
                      <button
                        type="button"
                        onClick={() => setView(a)}
                        className="rounded p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40 hover:text-pug-navy-700"
                        title="View"
                      >
                        <Eye className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => directDownload(a)}
                        className="rounded p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
                        title="Download"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                      {!locked && (
                        <button
                          type="button"
                          onClick={() => remove(a.id)}
                          className="rounded p-1 text-rose-600 hover:bg-rose-500/10"
                          title="Remove"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <AttachmentViewerModal
        open={view !== null}
        onClose={() => setView(null)}
        viewUrl={view ? `/api/v1/cases/${caseId}/attachments/${view.id}/view` : ''}
        downloadUrl={
          view ? `/api/v1/cases/${caseId}/attachments/${view.id}/download` : ''
        }
        filename={view?.original_filename ?? ''}
        mimeType={view?.mime_type ?? 'application/octet-stream'}
      />
    </div>
  );
}
