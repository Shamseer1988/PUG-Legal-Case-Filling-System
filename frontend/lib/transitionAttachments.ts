'use client';

import { API_BASE } from './api';
import { useAuthStore } from './auth';

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

/** Upload a file to be bound to the next transition. The returned
 *  attachment row is unbound until the transition is POSTed with
 *  its id in `attachment_ids[]`. */
export async function uploadTransitionAttachment(
  caseId: number,
  file: File,
): Promise<TransitionAttachment> {
  const token = useAuthStore.getState().accessToken;
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`${API_BASE}/api/v1/cases/${caseId}/transition-attachments`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: fd,
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body?.detail || `Upload failed (${r.status})`);
  }
  return r.json();
}

/** Fetch the file with the bearer token and return an object URL
 *  the caller can revoke when done. */
export async function downloadTransitionAttachment(
  caseId: number,
  attachmentId: number,
): Promise<{ url: string; revoke: () => void }> {
  const token = useAuthStore.getState().accessToken;
  const r = await fetch(
    `${API_BASE}/api/v1/cases/${caseId}/transition-attachments/${attachmentId}/download`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined },
  );
  if (!r.ok) throw new Error(`Download failed (${r.status})`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  return { url, revoke: () => URL.revokeObjectURL(url) };
}

export async function deletePendingTransitionAttachment(
  caseId: number,
  attachmentId: number,
): Promise<void> {
  const token = useAuthStore.getState().accessToken;
  const r = await fetch(
    `${API_BASE}/api/v1/cases/${caseId}/transition-attachments/${attachmentId}`,
    {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    },
  );
  if (!r.ok && r.status !== 204) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body?.detail || `Delete failed (${r.status})`);
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
