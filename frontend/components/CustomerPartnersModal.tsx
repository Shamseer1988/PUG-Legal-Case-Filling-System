'use client';

import { FileText, Pencil, Plus, Save, Trash2, Upload, Users, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

export type Partner = {
  id: number;
  customer_id: number;
  name: string;
  id_number: string;
  id_expiry_date: string | null;
  nationality: string;
  residency_status: 'inside_country' | 'outside_country' | 'visa_cancelled' | 'unknown';
  is_cheque_signatory: boolean;
  is_authorised_signatory: boolean;
  is_admin_contact: boolean;
  role_other: string;
  phone: string;
  email: string;
  notes: string;
  is_active: boolean;
  id_document_filename: string;
  id_document_mime: string;
  id_document_size: number;
};

type Draft = Omit<Partner, 'id' | 'customer_id' | 'id_document_filename' | 'id_document_mime' | 'id_document_size'>;

const EMPTY_DRAFT: Draft = {
  name: '',
  id_number: '',
  id_expiry_date: null,
  nationality: '',
  residency_status: 'inside_country',
  is_cheque_signatory: false,
  is_authorised_signatory: false,
  is_admin_contact: false,
  role_other: '',
  phone: '',
  email: '',
  notes: '',
  is_active: true,
};

const RESIDENCY_OPTIONS: { value: Draft['residency_status']; label: string }[] = [
  { value: 'inside_country', label: 'Inside Country' },
  { value: 'outside_country', label: 'Outside Country' },
  { value: 'visa_cancelled', label: 'Visa Cancelled' },
  { value: 'unknown', label: 'Unknown' },
];

type Props = {
  customerId: number;
  customerName: string;
  canWrite: boolean;
  onClose: () => void;
};

export function CustomerPartnersModal({
  customerId,
  customerName,
  canWrite,
  onClose,
}: Props) {
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | 'new' | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api<Partner[]>(
        `/api/v1/masters/customers/${customerId}/partners`,
      );
      setPartners(rows);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    reload();
  }, [reload]);

  function startCreate() {
    setDraft(EMPTY_DRAFT);
    setEditingId('new');
    setError(null);
  }
  function startEdit(p: Partner) {
    setDraft({
      name: p.name,
      id_number: p.id_number,
      id_expiry_date: p.id_expiry_date,
      nationality: p.nationality,
      residency_status: p.residency_status,
      is_cheque_signatory: p.is_cheque_signatory,
      is_authorised_signatory: p.is_authorised_signatory,
      is_admin_contact: p.is_admin_contact,
      role_other: p.role_other,
      phone: p.phone,
      email: p.email,
      notes: p.notes,
      is_active: p.is_active,
    });
    setEditingId(p.id);
    setError(null);
  }
  function cancelEdit() {
    setEditingId(null);
    setError(null);
  }

  async function save() {
    setError(null);
    try {
      const body = { ...draft, id_expiry_date: draft.id_expiry_date || null };
      if (editingId === 'new') {
        await api(`/api/v1/masters/customers/${customerId}/partners`, {
          method: 'POST',
          body,
        });
      } else if (typeof editingId === 'number') {
        await api(
          `/api/v1/masters/customers/${customerId}/partners/${editingId}`,
          { method: 'PATCH', body },
        );
      }
      setEditingId(null);
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function remove(p: Partner) {
    if (!confirm(`Remove partner "${p.name}"?`)) return;
    try {
      await api(`/api/v1/masters/customers/${customerId}/partners/${p.id}`, {
        method: 'DELETE',
      });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-2xl">
        <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-5 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            <Users className="h-4 w-4" /> Partners — {customerName}
          </h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {error}
            </div>
          )}

          {canWrite && editingId === null && (
            <div className="mb-3 flex justify-end">
              <button
                onClick={startCreate}
                className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
              >
                <Plus className="h-3.5 w-3.5" /> Add Partner
              </button>
            </div>
          )}

          {editingId !== null && (
            <PartnerEditor
              draft={draft}
              setDraft={setDraft}
              onSave={save}
              onCancel={cancelEdit}
              title={editingId === 'new' ? 'New Partner' : `Edit Partner #${editingId}`}
            />
          )}

          {loading ? (
            <div className="py-8 text-center text-sm text-[rgb(var(--color-muted))]">
              Loading…
            </div>
          ) : partners.length === 0 ? (
            <div className="py-8 text-center text-sm text-[rgb(var(--color-muted))]">
              No partners on file.
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-[rgb(var(--color-border))]">
              <table className="w-full text-sm">
                <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
                  <tr>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">ID #</th>
                    <th className="px-3 py-2">Nationality</th>
                    <th className="px-3 py-2">Residency</th>
                    <th className="px-3 py-2">Roles</th>
                    <th className="px-3 py-2">ID Doc</th>
                    {canWrite && <th className="px-3 py-2 text-right">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {partners.map((p) => (
                    <tr key={p.id} className="border-t border-[rgb(var(--color-border))]">
                      <td className="px-3 py-2 font-medium">{p.name}</td>
                      <td className="px-3 py-2">{p.id_number || '-'}</td>
                      <td className="px-3 py-2">{p.nationality || '-'}</td>
                      <td className="px-3 py-2">
                        {RESIDENCY_OPTIONS.find((r) => r.value === p.residency_status)?.label ?? p.residency_status}
                      </td>
                      <td className="px-3 py-2">
                        <RoleBadges p={p} />
                      </td>
                      <td className="px-3 py-2">
                        <IdDocCell
                          customerId={customerId}
                          partner={p}
                          canWrite={canWrite}
                          onChanged={reload}
                        />
                      </td>
                      {canWrite && (
                        <td className="px-3 py-2 text-right">
                          <button
                            onClick={() => startEdit(p)}
                            className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                          >
                            <Pencil className="h-3 w-3" /> Edit
                          </button>
                          <button
                            onClick={() => remove(p)}
                            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10"
                          >
                            <Trash2 className="h-3 w-3" /> Delete
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end border-t border-[rgb(var(--color-border))] px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function RoleBadges({ p }: { p: Partner }) {
  const badges: string[] = [];
  if (p.is_cheque_signatory) badges.push('Cheque Sig.');
  if (p.is_authorised_signatory) badges.push('Auth. Sig.');
  if (p.is_admin_contact) badges.push('Admin');
  if (p.role_other) badges.push(p.role_other);
  if (badges.length === 0) return <span className="text-xs text-[rgb(var(--color-muted))]">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b) => (
        <span
          key={b}
          className="rounded-full bg-pug-navy-700/10 px-2 py-0.5 text-[10px] font-semibold text-pug-navy-700 dark:bg-pug-navy-500/30 dark:text-pug-navy-100"
        >
          {b}
        </span>
      ))}
    </div>
  );
}

function IdDocCell({
  customerId,
  partner,
  canWrite,
  onChanged,
}: {
  customerId: number;
  partner: Partner;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const token = useAuthStore((s) => s.accessToken);

  async function upload(file: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(
        `${API_BASE}/api/v1/masters/customers/${customerId}/partners/${partner.id}/id-document`,
        {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: fd,
        },
      );
      if (!res.ok) throw new Error(await res.text());
      onChanged();
    } catch (e) {
      alert(`Upload failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function view() {
    const res = await fetch(
      `${API_BASE}/api/v1/masters/customers/${customerId}/partners/${partner.id}/id-document`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!res.ok) {
      alert('Could not load ID document.');
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  async function remove() {
    if (!confirm('Remove this ID document?')) return;
    setBusy(true);
    try {
      await api(
        `/api/v1/masters/customers/${customerId}/partners/${partner.id}/id-document`,
        { method: 'DELETE' },
      );
      onChanged();
    } catch (e) {
      alert(`Delete failed: ${(e as ApiError).message}`);
    } finally {
      setBusy(false);
    }
  }

  if (partner.id_document_filename) {
    return (
      <div className="flex items-center gap-2">
        <button
          onClick={view}
          title={partner.id_document_filename}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs hover:bg-[rgb(var(--color-border))]/40"
        >
          <FileText className="h-3 w-3" /> View
        </button>
        {canWrite && (
          <button
            onClick={remove}
            disabled={busy}
            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-rose-600 hover:bg-rose-500/10"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>
    );
  }

  if (!canWrite) {
    return <span className="text-xs text-[rgb(var(--color-muted))]">-</span>;
  }

  return (
    <label className="inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 text-xs hover:bg-[rgb(var(--color-border))]/40">
      {busy ? (
        <span className="text-[rgb(var(--color-muted))]">Uploading…</span>
      ) : (
        <>
          <Upload className="h-3 w-3" /> Upload
        </>
      )}
      <input
        type="file"
        className="hidden"
        accept="image/*,application/pdf"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (f) upload(f);
        }}
        disabled={busy}
      />
    </label>
  );
}

function PartnerEditor({
  draft,
  setDraft,
  onSave,
  onCancel,
  title,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  onSave: () => void;
  onCancel: () => void;
  title: string;
}) {
  const upd = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft({ ...draft, [k]: v });
  return (
    <div className="mb-4 rounded-lg border border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg))]/40 p-4">
      <div className="mb-3 text-sm font-semibold">{title}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Field label="Name *">
          <input
            value={draft.name}
            onChange={(e) => upd('name', e.target.value)}
            className={inputCls}
            required
          />
        </Field>
        <Field label="ID Number">
          <input
            value={draft.id_number}
            onChange={(e) => upd('id_number', e.target.value)}
            className={inputCls}
          />
        </Field>
        <Field label="ID Expiry Date">
          <input
            type="date"
            value={draft.id_expiry_date ?? ''}
            onChange={(e) => upd('id_expiry_date', e.target.value || null)}
            className={inputCls}
          />
        </Field>
        <Field label="Nationality">
          <input
            value={draft.nationality}
            onChange={(e) => upd('nationality', e.target.value)}
            className={inputCls}
          />
        </Field>
        <Field label="Residency Status">
          <select
            value={draft.residency_status}
            onChange={(e) => upd('residency_status', e.target.value as Draft['residency_status'])}
            className={inputCls}
          >
            {RESIDENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Phone">
          <input
            value={draft.phone}
            onChange={(e) => upd('phone', e.target.value)}
            className={inputCls}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            value={draft.email}
            onChange={(e) => upd('email', e.target.value)}
            className={inputCls}
          />
        </Field>
        <Field label="Other Role">
          <input
            value={draft.role_other}
            onChange={(e) => upd('role_other', e.target.value)}
            placeholder="e.g. Manager, Owner"
            className={inputCls}
          />
        </Field>
        <div className="md:col-span-2">
          <div className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
            Roles
          </div>
          <div className="flex flex-wrap gap-4">
            <Checkbox
              label="Cheque Signatory"
              value={draft.is_cheque_signatory}
              onChange={(v) => upd('is_cheque_signatory', v)}
            />
            <Checkbox
              label="Authorised Signatory"
              value={draft.is_authorised_signatory}
              onChange={(v) => upd('is_authorised_signatory', v)}
            />
            <Checkbox
              label="Admin Contact"
              value={draft.is_admin_contact}
              onChange={(v) => upd('is_admin_contact', v)}
            />
            <Checkbox
              label="Active"
              value={draft.is_active}
              onChange={(v) => upd('is_active', v)}
            />
          </div>
        </div>
        <Field label="Notes" className="md:col-span-2">
          <textarea
            rows={2}
            value={draft.notes}
            onChange={(e) => upd('notes', e.target.value)}
            className={inputCls}
          />
        </Field>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          onClick={onSave}
          className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-pug-navy-600"
        >
          <Save className="h-4 w-4" /> Save
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          <X className="h-4 w-4" /> Cancel
        </button>
      </div>
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

function Checkbox({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4"
      />
      {label}
    </label>
  );
}
