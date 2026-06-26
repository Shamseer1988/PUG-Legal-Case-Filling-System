'use client';

import { apiFetch } from './api';

export type TransitionAttachment = {
  id: number;
  case_id: number;
  transition_id: number | null;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by_id: number;
  uploaded_by_name: string;
  created_at: string;
};

export type TimelineEntry = {
  id: number;
  action_type: string;
  from_status: string;
  to_status: string;
  from_stage: string;
  to_stage: string;
  actor_id: number;
  actor_name: string;
  comment: string;
  created_at: string;
  attachments: TransitionAttachment[];
};

async function extractError(r: Response, fallback: string): Promise<string> {
  const body = await r.json().catch(() => null as unknown);
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return `${fallback} (${r.status})`;
}

/** Upload a file to be bound to the next transition. The returned
 *  attachment row is unbound until the transition is POSTed with
 *  its id in `attachment_ids[]`. Uses `apiFetch` so a 401 triggers
 *  the shared refresh-or-redirect flow. */
export async function uploadTransitionAttachment(
  caseId: number,
  file: File,
): Promise<TransitionAttachment> {
  const fd = new FormData();
  fd.append('file', file);
  const r = await apiFetch(`/api/v1/cases/${caseId}/transition-attachments`, {
    method: 'POST',
    body: fd,
  });
  if (!r.ok) throw new Error(await extractError(r, 'Upload failed'));
  return r.json();
}

/** Fetch the file with the bearer token and return an object URL
 *  the caller can revoke when done. */
export async function downloadTransitionAttachment(
  caseId: number,
  attachmentId: number,
): Promise<{ url: string; revoke: () => void }> {
  const r = await apiFetch(
    `/api/v1/cases/${caseId}/transition-attachments/${attachmentId}/download`,
  );
  if (!r.ok) throw new Error(await extractError(r, 'Download failed'));
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  return { url, revoke: () => URL.revokeObjectURL(url) };
}

export async function deletePendingTransitionAttachment(
  caseId: number,
  attachmentId: number,
): Promise<void> {
  const r = await apiFetch(
    `/api/v1/cases/${caseId}/transition-attachments/${attachmentId}`,
    { method: 'DELETE' },
  );
  if (!r.ok && r.status !== 204) {
    throw new Error(await extractError(r, 'Delete failed'));
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
