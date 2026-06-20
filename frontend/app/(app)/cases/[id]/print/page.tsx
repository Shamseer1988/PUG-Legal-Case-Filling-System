'use client';

import { useParams, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { Printer, X } from 'lucide-react';
import { API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

/** Authenticated inline PDF viewer for the case print form.
 *
 * Why the indirection: the backend serves a binary PDF behind a
 * bearer-token guard. A plain ``<a href={apiUrl}>`` opens a new tab
 * without the Authorization header, which is what produced the
 * ``{"detail":"Authentication required"}`` users were seeing. We
 * fetch the bytes with the token, hand them to the browser as a
 * blob URL, and let the native PDF viewer render them inside an
 * iframe — same pattern the Finance App uses for voucher prints.
 */
export default function CasePrintPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const token = useAuthStore((s) => s.accessToken);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const printedRef = useRef(false);

  useEffect(() => {
    if (!id || !token) {
      if (!token) setErr('Not signed in.');
      return;
    }
    let cancelled = false;
    let createdUrl: string | null = null;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/v1/cases/${id}/print`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!r.ok) {
          if (!cancelled) setErr(`Print failed (${r.status} ${r.statusText})`);
          return;
        }
        const bytes = await r.blob();
        // Ensure the blob is tagged application/pdf; some browsers ignore
        // a server-provided type when rendering via blob: URLs.
        const pdfBlob = bytes.type === 'application/pdf'
          ? bytes
          : new Blob([bytes], { type: 'application/pdf' });
        createdUrl = URL.createObjectURL(pdfBlob);
        if (cancelled) {
          URL.revokeObjectURL(createdUrl);
          return;
        }
        setBlobUrl(createdUrl);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message || 'Print failed');
      }
    })();
    return () => {
      cancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [id, token]);

  function triggerPrint() {
    const f = iframeRef.current;
    if (!f) return;
    try {
      f.contentWindow?.focus();
      f.contentWindow?.print();
    } catch {
      // Fallback to top-level print if the iframe is sandboxed.
      window.print();
    }
  }

  function onIframeLoad() {
    if (printedRef.current) return;
    printedRef.current = true;
    // Give the embedded PDF viewer a beat to paint before invoking print.
    setTimeout(triggerPrint, 400);
  }

  if (err) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
        <button
          onClick={() => router.back()}
          className="mt-4 inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          <X className="h-4 w-4" /> Close
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      {/* Toolbar (hidden when the browser is actually printing) */}
      <div className="print:hidden flex items-center justify-between rounded-md border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] px-3 py-2">
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Preview opens in your browser&apos;s PDF viewer. Use the toolbar to print or download.
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={triggerPrint}
            disabled={!blobUrl}
            className="inline-flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
          >
            <Printer className="h-3.5 w-3.5" /> Print
          </button>
          <button
            onClick={() => router.back()}
            className="inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-xs hover:bg-[rgb(var(--color-border))]/40"
          >
            <X className="h-3.5 w-3.5" /> Close
          </button>
        </div>
      </div>

      {blobUrl ? (
        <iframe
          ref={iframeRef}
          title="Case print preview"
          src={blobUrl}
          onLoad={onIframeLoad}
          className="flex-1 w-full rounded-md border border-[rgb(var(--color-border))] bg-white"
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-sm text-[rgb(var(--color-muted))]">
          Preparing print preview...
        </div>
      )}
    </div>
  );
}
