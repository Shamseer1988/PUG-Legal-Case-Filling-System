'use client';

import { Download, Printer, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

/**
 * Phase 36: shared preview modal for every attachment surface.
 *
 *   - Fetches the file via the ``/view`` endpoint (Content-Disposition: inline)
 *     so the browser embeds it rather than triggering a save dialog.
 *   - Holds the bytes as a blob URL so Download + Print don't re-hit
 *     the backend.
 *   - PDFs render in an <iframe>; images render in an <img>; everything
 *     else gets a "Not previewable" message with a Download button.
 *
 * Caller passes the canonical ``viewUrl`` (already includes the
 * ``/view`` segment) so this component works for case, cheque and
 * transition attachments without per-kind branches.
 */
type Props = {
  open: boolean;
  onClose: () => void;
  viewUrl: string;
  downloadUrl: string;
  filename: string;
  mimeType: string;
};

export function AttachmentViewerModal({
  open,
  onClose,
  viewUrl,
  downloadUrl,
  filename,
  mimeType,
}: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    let url: string | null = null;
    setErr(null);
    setBlobUrl(null);
    (async () => {
      try {
        const token = useAuthStore.getState().accessToken;
        const r = await fetch(`${API_BASE}${viewUrl}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!r.ok) {
          throw new Error(`Could not load file (${r.status})`);
        }
        const blob = await r.blob();
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [open, viewUrl]);

  function downloadBlob() {
    if (!blobUrl) {
      // Fall back to a direct hit if the blob isn't ready (rare).
      window.open(`${API_BASE}${downloadUrl}`, '_blank');
      return;
    }
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    a.click();
  }

  function printFile() {
    const win = iframeRef.current?.contentWindow;
    if (!win) {
      // Image case (no iframe). Open the blob in a new tab and let
      // the user invoke print from there.
      if (blobUrl) window.open(blobUrl, '_blank');
      return;
    }
    try {
      win.focus();
      win.print();
    } catch {
      if (blobUrl) window.open(blobUrl, '_blank');
    }
  }

  if (!open) return null;

  const isPdf = mimeType === 'application/pdf';
  const isImage = mimeType.startsWith('image/');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex h-full max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-2xl">
        <div className="flex shrink-0 items-center justify-between border-b border-[rgb(var(--color-border))] px-4 py-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{filename}</div>
            <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
              {mimeType}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={downloadBlob}
              className="inline-flex items-center gap-1 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
            >
              <Download className="h-3.5 w-3.5" /> Download
            </button>
            <button
              onClick={printFile}
              disabled={!blobUrl}
              className="inline-flex items-center gap-1 rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-50"
            >
              <Printer className="h-3.5 w-3.5" /> Print
            </button>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto bg-[rgb(var(--color-bg))]">
          {err && (
            <div className="m-4 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {err}
            </div>
          )}
          {!err && !blobUrl && (
            <div className="flex h-full items-center justify-center text-xs text-[rgb(var(--color-muted))]">
              Loading…
            </div>
          )}
          {blobUrl && isPdf && (
            <iframe
              ref={iframeRef}
              src={blobUrl}
              title={filename}
              className="h-full w-full border-0 bg-white"
            />
          )}
          {blobUrl && isImage && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={blobUrl}
              alt={filename}
              className="mx-auto block max-h-full max-w-full"
            />
          )}
          {blobUrl && !isPdf && !isImage && (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
              <div className="text-sm text-[rgb(var(--color-muted))]">
                Preview not available for this file type.
              </div>
              <button
                onClick={downloadBlob}
                className="inline-flex items-center gap-1 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
              >
                <Download className="h-4 w-4" /> Download
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
