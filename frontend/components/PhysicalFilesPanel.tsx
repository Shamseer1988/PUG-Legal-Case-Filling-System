'use client';

import {
  AlertTriangle,
  ArrowRightLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  FileSignature,
  Plus,
  Save,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { assertUploadSize, MAX_IMAGE_BYTES } from '@/lib/uploadLimits';
import { useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';

/** Phase 41 + 45: per-case physical document chain of custody.
 *
 * Phase 45 adds a two-phase transfer flow: the sender initiates a transfer
 * (status=pending), and the named recipient must explicitly Accept it before
 * custody moves. Receiver can also Reject, which leaves custody with the sender.
 * Recipient uploads a signed acknowledgment at acceptance time.
 */

type CustodyLog = {
  id: number;
  document_id: number;
  transferred_at: string;
  recorded_by_user_id: number | null;
  from_user_id: number | null;
  to_user_id: number | null;
  location_id: number | null;
  location_text: string;
  note: string;
  signature_filename: string;
  signature_size: number;
  signature_mime: string;
  from_user_name: string;
  to_user_name: string;
  location_name: string;
  recorded_by_name: string;
  // Phase 45
  transfer_status: string;
  accepted_at: string | null;
  ack_filename: string;
  ack_size: number;
  ack_mime: string;
};

type DocRow = {
  id: number;
  case_id: number;
  kind: string;
  label: string;
  notes: string;
  is_active: boolean;
  current_holder_user_id: number | null;
  current_location_id: number | null;
  current_location_text: string;
  last_transferred_at: string | null;
  current_holder_name: string;
  current_location_name: string;
  case_no: string;
  // Phase 45
  pending_transfer_log_id: number | null;
  pending_transfer_to_user_id: number | null;
  pending_transfer_to_name: string;
};

type DocDetail = DocRow & { custody_log: CustodyLog[] };

type UserOption = { id: number; full_name: string; email: string };

const KIND_OPTIONS: { value: string; label: string }[] = [
  { value: 'case_folder', label: 'Case Folder' },
  { value: 'original_cheque', label: 'Original Cheque' },
  { value: 'id_copy', label: 'ID Copy' },
  { value: 'contract', label: 'Contract' },
  { value: 'court_filing', label: 'Court Filing' },
  { value: 'bank_letter', label: 'Bank Letter' },
  { value: 'other', label: 'Other' },
];

type Props = {
  caseId: number;
  canTransfer: boolean;
};

export function PhysicalFilesPanel({ caseId, canTransfer }: Props) {
  const [rows, setRows] = useState<DocRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [transferFor, setTransferFor] = useState<DocRow | null>(null);
  const [acceptFor, setAcceptFor] = useState<DocRow | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [details, setDetails] = useState<Record<number, DocDetail>>({});

  const me = useAuthStore((s) => s.me);
  const locations = useMasterOptions('/api/v1/masters/document-locations', 'name');

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<DocRow[]>(`/api/v1/cases/${caseId}/documents`);
      setRows(data);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function expand(d: DocRow) {
    if (expandedId === d.id) {
      setExpandedId(null);
      return;
    }
    if (!details[d.id]) {
      try {
        const detail = await api<DocDetail>(`/api/v1/documents/${d.id}`);
        setDetails((prev) => ({ ...prev, [d.id]: detail }));
      } catch (e) {
        setError((e as ApiError).message);
        return;
      }
    }
    setExpandedId(d.id);
  }

  async function retire(d: DocRow) {
    if (!confirm(`Retire "${d.label}"? Its log stays for audit.`)) return;
    try {
      await api(`/api/v1/documents/${d.id}`, { method: 'DELETE' });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function reject(d: DocRow) {
    if (!d.pending_transfer_log_id) return;
    if (!confirm(`Reject the incoming transfer of "${d.label}"?`)) return;
    try {
      await api(`/api/v1/documents/transfers/${d.pending_transfer_log_id}/reject`, {
        method: 'POST',
        body: {},
      });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  // Docs with a pending incoming transfer for the current user
  const pendingForMe = rows.filter(
    (d) =>
      d.pending_transfer_log_id !== null &&
      d.pending_transfer_to_user_id === me?.id,
  );

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Physical Files
          {pendingForMe.length > 0 && (
            <span className="ml-2 rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
              {pendingForMe.length} pending
            </span>
          )}
        </h2>
        {canTransfer && !adding && (
          <button
            onClick={() => setAdding(true)}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-3.5 w-3.5" /> Register Document
          </button>
        )}
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      {adding && canTransfer && (
        <RegisterForm
          caseId={caseId}
          locations={locations}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            reload();
          }}
        />
      )}

      {/* Incoming-transfer alert banner */}
      {pendingForMe.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-400/60 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
          <div className="mb-1 font-semibold flex items-center gap-1.5">
            <Clock className="h-4 w-4" /> Awaiting your acceptance ({pendingForMe.length})
          </div>
          <ul className="space-y-1 text-xs">
            {pendingForMe.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3">
                <span>
                  <strong>{d.label}</strong> — transferred to you
                </span>
                <div className="flex gap-1.5 shrink-0">
                  <button
                    onClick={() => setAcceptFor(d)}
                    className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-emerald-500"
                  >
                    <Check className="h-3 w-3" /> Accept
                  </button>
                  <button
                    onClick={() => reject(d)}
                    className="inline-flex items-center gap-1 rounded border border-rose-400/60 px-2 py-0.5 text-[10px] text-rose-700 hover:bg-rose-500/10"
                  >
                    <XCircle className="h-3 w-3" /> Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading ? (
        <div className="py-8 text-center text-sm text-[rgb(var(--color-muted))]">
          Loading…
        </div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center text-sm text-[rgb(var(--color-muted))]">
          No physical documents registered for this case.
          <div className="mt-1 text-[10px]">
            A &quot;Case Folder&quot; row is auto-created when a new case is filed;
            older cases need a one-time Register Document.
          </div>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[rgb(var(--color-border))]">
          <table className="w-full text-sm">
            <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
              <tr>
                <th className="w-6 px-2"></th>
                <th className="px-3 py-2">Document</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2">Currently with</th>
                <th className="px-3 py-2">Location</th>
                <th className="px-3 py-2">Last move</th>
                {canTransfer && <th className="px-3 py-2 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const expanded = expandedId === d.id;
                const detail = details[d.id];
                const isPendingToMe =
                  d.pending_transfer_log_id !== null &&
                  d.pending_transfer_to_user_id === me?.id;
                const isPendingToOther =
                  d.pending_transfer_log_id !== null &&
                  d.pending_transfer_to_user_id !== me?.id;
                return (
                  <Fragment key={d.id}>
                    <tr
                      className={`border-t border-[rgb(var(--color-border))] ${
                        d.is_active ? '' : 'opacity-50'
                      }`}
                    >
                      <td className="px-2 py-2">
                        <button
                          onClick={() => expand(d)}
                          className="rounded p-1 hover:bg-[rgb(var(--color-border))]/40"
                          aria-label={expanded ? 'Collapse log' : 'Expand log'}
                        >
                          {expanded ? (
                            <ChevronDown className="h-3 w-3" />
                          ) : (
                            <ChevronRight className="h-3 w-3" />
                          )}
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{d.label}</div>
                        {d.notes && (
                          <div className="text-[10px] text-[rgb(var(--color-muted))]">
                            {d.notes}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {KIND_OPTIONS.find((k) => k.value === d.kind)?.label ?? d.kind}
                      </td>
                      <td className="px-3 py-2">
                        {isPendingToMe ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                            <Clock className="h-3 w-3" /> Pending — accept from {d.current_holder_name || 'sender'}
                          </span>
                        ) : isPendingToOther ? (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                            <Clock className="h-3 w-3" />
                            {d.current_holder_name || '—'}{' '}
                            <span className="opacity-70">→ pending to {d.pending_transfer_to_name}</span>
                          </span>
                        ) : (
                          d.current_holder_name || (
                            <span className="text-xs text-[rgb(var(--color-muted))]">
                              {d.current_location_name ? '(in storage)' : '-'}
                            </span>
                          )
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {d.current_location_name || d.current_location_text || '-'}
                      </td>
                      <td className="px-3 py-2 text-xs">
                        {d.last_transferred_at
                          ? new Date(d.last_transferred_at).toLocaleString()
                          : '-'}
                      </td>
                      {canTransfer && (
                        <td className="px-3 py-2 text-right">
                          {d.is_active && (
                            <>
                              {isPendingToMe ? (
                                <>
                                  <button
                                    onClick={() => setAcceptFor(d)}
                                    className="mr-2 inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-500"
                                  >
                                    <Check className="h-3 w-3" /> Accept
                                  </button>
                                  <button
                                    onClick={() => reject(d)}
                                    className="inline-flex items-center gap-1 rounded border border-rose-400/60 px-2 py-1 text-xs text-rose-700 hover:bg-rose-500/10"
                                  >
                                    <XCircle className="h-3 w-3" /> Reject
                                  </button>
                                </>
                              ) : !isPendingToOther ? (
                                <>
                                  <button
                                    onClick={() => setTransferFor(d)}
                                    className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                                  >
                                    <ArrowRightLeft className="h-3 w-3" /> Transfer
                                  </button>
                                  <button
                                    onClick={() => retire(d)}
                                    className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10"
                                  >
                                    <Trash2 className="h-3 w-3" /> Retire
                                  </button>
                                </>
                              ) : (
                                <span className="text-[10px] text-[rgb(var(--color-muted))]">
                                  Awaiting recipient
                                </span>
                              )}
                            </>
                          )}
                        </td>
                      )}
                    </tr>
                    {expanded && detail && (
                      <tr className="border-t border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg))]/30">
                        <td colSpan={canTransfer ? 7 : 6} className="px-6 py-3">
                          <CustodyTimeline log={detail.custody_log} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {transferFor && (
        <TransferModal
          doc={transferFor}
          locations={locations}
          onClose={() => setTransferFor(null)}
          onSaved={() => {
            setTransferFor(null);
            setDetails((prev) => {
              const next = { ...prev };
              delete next[transferFor.id];
              return next;
            });
            reload();
          }}
        />
      )}

      {acceptFor && (
        <AcceptModal
          doc={acceptFor}
          onClose={() => setAcceptFor(null)}
          onSaved={() => {
            setAcceptFor(null);
            setDetails((prev) => {
              const next = { ...prev };
              delete next[acceptFor.id];
              return next;
            });
            reload();
          }}
        />
      )}
    </section>
  );
}

function RegisterForm({
  caseId,
  locations,
  onClose,
  onSaved,
}: {
  caseId: number;
  locations: { value: number; label: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState({
    label: '',
    kind: 'original_cheque',
    notes: '',
    initial_location_id: null as number | null,
    initial_location_text: '',
    initial_note: '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/cases/${caseId}/documents`, {
        method: 'POST',
        body: {
          label: draft.label,
          kind: draft.kind,
          notes: draft.notes,
          initial_location_id: draft.initial_location_id ?? undefined,
          initial_location_text: draft.initial_location_text,
          initial_note: draft.initial_note,
        },
      });
      onSaved();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-3 rounded-lg border border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg))]/40 p-4">
      <div className="mb-2 text-sm font-semibold">New Physical Document</div>
      {err && (
        <div className="mb-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-xs text-rose-700">
          {err}
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Label *">
          <input
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
            className={inputCls}
            placeholder="e.g. Original Cheque #00123"
          />
        </Field>
        <Field label="Kind">
          <select
            value={draft.kind}
            onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            className={inputCls}
          >
            {KIND_OPTIONS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Initial storage location">
          <select
            value={draft.initial_location_id ?? ''}
            onChange={(e) =>
              setDraft({
                ...draft,
                initial_location_id: e.target.value === '' ? null : Number(e.target.value),
              })
            }
            className={inputCls}
          >
            <option value="">-- (no location yet)</option>
            {locations.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Or free-text location">
          <input
            value={draft.initial_location_text}
            onChange={(e) => setDraft({ ...draft, initial_location_text: e.target.value })}
            className={inputCls}
            placeholder="e.g. With courier ABC #1234"
          />
        </Field>
        <Field label="Notes" className="md:col-span-2">
          <textarea
            rows={2}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            className={inputCls}
            placeholder="Anything distinctive about this physical item"
          />
        </Field>
        <Field label="Registration note" className="md:col-span-2">
          <input
            value={draft.initial_note}
            onChange={(e) => setDraft({ ...draft, initial_note: e.target.value })}
            className={inputCls}
            placeholder="Shown as the first row in the custody log"
          />
        </Field>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          onClick={save}
          disabled={busy || !draft.label.trim()}
          className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
        >
          <Save className="h-4 w-4" /> Register
        </button>
        <button
          onClick={onClose}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          <X className="h-4 w-4" /> Cancel
        </button>
      </div>
    </div>
  );
}

function TransferModal({
  doc,
  locations,
  onClose,
  onSaved,
}: {
  doc: DocRow;
  locations: { value: number; label: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [users, setUsers] = useState<UserOption[]>([]);
  const [draft, setDraft] = useState({
    to_user_id: null as number | null,
    to_location_id: null as number | null,
    location_text: '',
    note: '',
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [signature, setSignature] = useState<File | null>(null);
  const token = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    api<UserOption[]>('/api/v1/users/options')
      .then(setUsers)
      .catch(() => setUsers([]));
  }, []);

  async function save() {
    if (
      draft.to_user_id == null &&
      draft.to_location_id == null &&
      !draft.location_text.trim()
    ) {
      setErr('Pick a recipient, a location, or write a free-text destination.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const detail = await api<DocDetail>(
        `/api/v1/documents/${doc.id}/transfer`,
        {
          method: 'POST',
          body: {
            to_user_id: draft.to_user_id ?? undefined,
            to_location_id: draft.to_location_id ?? undefined,
            location_text: draft.location_text,
            note: draft.note,
          },
        },
      );
      if (signature) {
        const logId = detail.custody_log[0]?.id;
        if (logId) {
          assertUploadSize(signature, MAX_IMAGE_BYTES);
          const fd = new FormData();
          fd.append('file', signature);
          const sig = await fetch(
            `${API_BASE}/api/v1/documents/transfers/${logId}/signature`,
            {
              method: 'POST',
              headers: token ? { Authorization: `Bearer ${token}` } : {},
              body: fd,
            },
          );
          if (!sig.ok) throw new Error(await sig.text());
        }
      }
      onSaved();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const recipientIsUser = draft.to_user_id != null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-xl rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            <ArrowRightLeft className="h-4 w-4" /> Transfer — {doc.label}
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4">
          {err && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>{err}</div>
            </div>
          )}

          <div className="mb-3 text-xs text-[rgb(var(--color-muted))]">
            Currently with{' '}
            <strong>
              {doc.current_holder_name ||
                doc.current_location_name ||
                doc.current_location_text ||
                'nobody'}
            </strong>
            .
          </div>

          {recipientIsUser && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-400/40 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
              <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                Transfers to a named user require their acceptance before custody moves.
                They will see an &quot;Accept&quot; prompt when they open this case.
              </span>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3">
            <Field label="Transfer to user">
              <select
                value={draft.to_user_id ?? ''}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    to_user_id: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
                className={inputCls}
              >
                <option value="">-- (location only)</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.email})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Destination location">
              <select
                value={draft.to_location_id ?? ''}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    to_location_id: e.target.value === '' ? null : Number(e.target.value),
                  })
                }
                className={inputCls}
              >
                <option value="">-- (no master location)</option>
                {locations.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Or free-text destination">
              <input
                value={draft.location_text}
                onChange={(e) => setDraft({ ...draft, location_text: e.target.value })}
                className={inputCls}
                placeholder="e.g. Courier ABC waybill #4567"
              />
            </Field>
            <Field label="Handover note">
              <textarea
                rows={2}
                value={draft.note}
                onChange={(e) => setDraft({ ...draft, note: e.target.value })}
                className={inputCls}
                placeholder="What's being handed over, why, expected return..."
              />
            </Field>
            {!recipientIsUser && (
              <Field label="Optional receipt / signature (photo)">
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setSignature(e.target.files?.[0] ?? null)}
                  className={inputCls}
                />
                {signature && (
                  <div className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">
                    Will upload: {signature.name}
                  </div>
                )}
                <div className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">
                  For location-only transfers. When sending to a user, they upload
                  the signed acknowledgment when accepting.
                </div>
              </Field>
            )}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[rgb(var(--color-border))] px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {recipientIsUser ? 'Send Transfer Request' : 'Record Transfer'}
          </button>
        </div>
      </div>
    </div>
  );
}

function AcceptModal({
  doc,
  onClose,
  onSaved,
}: {
  doc: DocRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [note, setNote] = useState('');
  const [ackFile, setAckFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const token = useAuthStore((s) => s.accessToken);

  async function accept() {
    if (!doc.pending_transfer_log_id) return;
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/documents/transfers/${doc.pending_transfer_log_id}/accept`, {
        method: 'POST',
        body: { note },
      });
      if (ackFile) {
        assertUploadSize(ackFile);
        const fd = new FormData();
        fd.append('file', ackFile);
        const res = await fetch(
          `${API_BASE}/api/v1/documents/transfers/${doc.pending_transfer_log_id}/acknowledgment`,
          {
            method: 'POST',
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: fd,
          },
        );
        if (!res.ok) throw new Error(await res.text());
      }
      onSaved();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
            <Check className="h-4 w-4" /> Accept Transfer — {doc.label}
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4">
          {err && (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>{err}</div>
            </div>
          )}

          <p className="mb-4 text-sm text-[rgb(var(--color-text))]">
            You are confirming receipt of{' '}
            <strong>&quot;{doc.label}&quot;</strong>. Accepting this transfer will
            move the file&apos;s custody to you in the system.
          </p>

          <div className="space-y-3">
            <Field label="Acceptance note (optional)">
              <textarea
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className={inputCls}
                placeholder="Any remarks about the handover condition..."
              />
            </Field>
            <Field label="Signed acknowledgment (upload)">
              <input
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => setAckFile(e.target.files?.[0] ?? null)}
                className={inputCls}
              />
              {ackFile && (
                <div className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">
                  Will upload: {ackFile.name}
                </div>
              )}
              <div className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">
                Upload a photo or scan of the signed handover slip. This serves as
                your acknowledgment of receipt and is required for court filings.
              </div>
            </Field>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[rgb(var(--color-border))] px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            Cancel
          </button>
          <button
            onClick={accept}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            <Check className="h-4 w-4" /> Confirm Receipt
          </button>
        </div>
      </div>
    </div>
  );
}

function CustodyTimeline({ log }: { log: CustodyLog[] }) {
  const token = useAuthStore((s) => s.accessToken);
  const ordered = useMemo(() => log, [log]);

  async function openFile(url: string) {
    const res = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      alert('Could not load file.');
      return;
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  }

  return (
    <div className="space-y-2">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        Chain of custody ({ordered.length} entr{ordered.length === 1 ? 'y' : 'ies'})
      </div>
      <ol className="space-y-2">
        {ordered.map((l) => {
          const isPending = l.transfer_status === 'pending';
          const isRejected = l.transfer_status === 'rejected';
          return (
            <li
              key={l.id}
              className={`rounded-md border px-3 py-2 text-xs ${
                isPending
                  ? 'border-amber-400/60 bg-amber-50 dark:bg-amber-900/20'
                  : isRejected
                  ? 'border-rose-400/40 bg-rose-50/50 opacity-60 dark:bg-rose-900/10'
                  : 'border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))]'
              }`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div>
                  <strong>
                    {l.from_user_name || '—'} → {l.to_user_name || '(storage)'}
                  </strong>
                  {l.location_name && (
                    <span className="ml-2 text-[rgb(var(--color-muted))]">
                      @ {l.location_name}
                    </span>
                  )}
                  {l.location_text && !l.location_name && (
                    <span className="ml-2 text-[rgb(var(--color-muted))]">
                      @ {l.location_text}
                    </span>
                  )}
                  {isPending && (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-500 px-1.5 py-0.5 text-[9px] font-bold text-white">
                      <Clock className="h-2.5 w-2.5" /> PENDING
                    </span>
                  )}
                  {isRejected && (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-rose-500 px-1.5 py-0.5 text-[9px] font-bold text-white">
                      REJECTED
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-[rgb(var(--color-muted))]">
                  {new Date(l.transferred_at).toLocaleString()}
                  {l.accepted_at && (
                    <span className="ml-1 text-emerald-600 dark:text-emerald-400">
                      · accepted {new Date(l.accepted_at).toLocaleString()}
                    </span>
                  )}
                  {l.recorded_by_name && (
                    <span> · recorded by {l.recorded_by_name}</span>
                  )}
                </div>
              </div>
              {l.note && (
                <div className="mt-1 whitespace-pre-wrap text-[rgb(var(--color-text))]">
                  {l.note}
                </div>
              )}
              <div className="mt-1 flex flex-wrap gap-2">
                {l.signature_filename && (
                  <button
                    onClick={() =>
                      openFile(`${API_BASE}/api/v1/documents/transfers/${l.id}/signature`)
                    }
                    className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] hover:bg-[rgb(var(--color-border))]/40"
                  >
                    <FileSignature className="h-3 w-3" /> View sender receipt
                  </button>
                )}
                {l.ack_filename && (
                  <button
                    onClick={() =>
                      openFile(
                        `${API_BASE}/api/v1/documents/transfers/${l.id}/acknowledgment`,
                      )
                    }
                    className="inline-flex items-center gap-1 rounded bg-emerald-600/10 px-2 py-0.5 text-[10px] text-emerald-700 hover:bg-emerald-600/20 dark:text-emerald-400"
                  >
                    <Check className="h-3 w-3" /> View signed acknowledgment
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className ?? ''}`}>
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}
