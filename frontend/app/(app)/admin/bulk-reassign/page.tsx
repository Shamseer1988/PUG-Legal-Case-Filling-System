'use client';

import { ArrowRight, ArrowRightLeft, Send } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type UserOption = {
  id: number;
  full_name: string;
  email: string;
  role_name: string;
};

const FIELD_OPTIONS: { value: string; label: string; role: string }[] = [
  { value: 'sales_manager_id', label: 'Sales Manager', role: 'Sales Manager' },
  { value: 'division_manager_id', label: 'Division Manager', role: 'Division Manager' },
  { value: 'auditor_id', label: 'Auditor', role: 'Auditor' },
  { value: 'fm_id', label: 'Finance Manager', role: 'Finance Manager' },
  { value: 'ed_id', label: 'Executive Director', role: 'Executive Director' },
  { value: 'chairman_id', label: 'Chairman / MD', role: 'Chairman / MD' },
];

export default function BulkReassignPage() {
  const [field, setField] = useState(FIELD_OPTIONS[0]);
  const [fromUserId, setFromUserId] = useState<number | ''>('');
  const [toUserId, setToUserId] = useState<number | ''>('');
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [options, setOptions] = useState<UserOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    updated: number;
    skipped_closed: number;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Whenever the role changes, refresh the user dropdowns to that
  // role's pool (admin can still reassign across the full universe,
  // but the typical workflow is "swap one Sales Manager for another").
  useEffect(() => {
    let cancelled = false;
    setFromUserId('');
    setToUserId('');
    setResult(null);
    setErr(null);
    (async () => {
      try {
        const opts = await api<UserOption[]>(
          `/api/v1/users/options?role=${encodeURIComponent(field.role)}`,
        );
        if (!cancelled) setOptions(opts);
      } catch (e) {
        if (!cancelled) setErr((e as ApiError).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [field]);

  async function submit() {
    if (!fromUserId || !toUserId) {
      setErr('Pick both source and target users.');
      return;
    }
    if (fromUserId === toUserId) {
      setErr('Source and target must differ.');
      return;
    }
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const r = await api<{ updated: number; skipped_closed: number }>(
        '/api/v1/admin/cases/bulk-reassign',
        {
          method: 'POST',
          body: {
            user_field: field.value,
            from_user_id: Number(fromUserId),
            to_user_id: Number(toUserId),
            only_open: onlyOpen,
          },
        },
      );
      setResult(r);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <ArrowRightLeft className="h-5 w-5" /> Bulk Reassignment
        </h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Transfer every case currently assigned to one signatory over
          to another. Useful when someone leaves the company or moves
          divisions.
        </p>
      </div>

      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <div className="space-y-4">
          <Field label="Signatory role to reassign">
            <select
              value={field.value}
              onChange={(e) => {
                const next = FIELD_OPTIONS.find((f) => f.value === e.target.value);
                if (next) setField(next);
              }}
              className={inputCls}
            >
              {FIELD_OPTIONS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </Field>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr] md:items-end">
            <Field label="From (current signatory)">
              <select
                value={fromUserId}
                onChange={(e) =>
                  setFromUserId(e.target.value ? Number(e.target.value) : '')
                }
                className={inputCls}
              >
                <option value="">Pick a user...</option>
                {options.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.email})
                  </option>
                ))}
              </select>
            </Field>
            <div className="flex h-10 items-center justify-center text-[rgb(var(--color-muted))]">
              <ArrowRight className="h-5 w-5" />
            </div>
            <Field label="To (new signatory)">
              <select
                value={toUserId}
                onChange={(e) =>
                  setToUserId(e.target.value ? Number(e.target.value) : '')
                }
                className={inputCls}
              >
                <option value="">Pick a user...</option>
                {options.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.email})
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={onlyOpen}
              onChange={(e) => setOnlyOpen(e.target.checked)}
              className="h-4 w-4"
            />
            Only reassign open cases (preserves Closed / Rejected history)
          </label>

          {err && (
            <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {err}
            </div>
          )}
          {result && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm">
              Reassigned <strong>{result.updated}</strong> case(s).
              {result.skipped_closed > 0 && (
                <>
                  {' '}
                  Skipped <strong>{result.skipped_closed}</strong> closed /
                  rejected case(s).
                </>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={submit}
            disabled={busy || !fromUserId || !toUserId}
            className="inline-flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {busy ? 'Reassigning...' : 'Reassign cases'}
          </button>
        </div>
      </section>
    </div>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}
