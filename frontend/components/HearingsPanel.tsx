'use client';

import { Calendar, Plus, Save, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';

type Hearing = {
  id: number;
  case_id: number;
  hearing_date: string;
  location: string;
  hearing_type: string;
  outcome: string;
  next_hearing_date: string | null;
  recorded_by_name: string;
  created_at: string;
};

const HEARING_TYPES = [
  'First Hearing',
  'Adjournment',
  'Plea',
  'Trial',
  'Cross Examination',
  'Judgment',
  'Appeal',
  'Other',
];

type Props = { caseId: number; status: string };

export function HearingsPanel({ caseId, status }: Props) {
  const me = useAuthStore((s) => s.me);
  const canWrite = hasPermission(me, 'hearings:write');
  const [rows, setRows] = useState<Hearing[]>([]);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    hearing_date: '',
    location: '',
    hearing_type: 'First Hearing',
    outcome: '',
    next_hearing_date: '',
  });

  async function load() {
    try {
      setRows(await api<Hearing[]>(`/api/v1/cases/${caseId}/hearings`));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    load();
  }, [caseId]);

  const blocked = status !== 'Approved' && status !== 'Filed';

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/v1/cases/${caseId}/hearings`, {
        method: 'POST',
        body: {
          ...draft,
          next_hearing_date: draft.next_hearing_date || null,
        },
      });
      setAdding(false);
      setDraft({
        hearing_date: '',
        location: '',
        hearing_type: 'First Hearing',
        outcome: '',
        next_hearing_date: '',
      });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm('Delete this hearing entry?')) return;
    try {
      await api(`/api/v1/cases/${caseId}/hearings/${id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
      <div className="mb-3 flex items-center gap-2">
        <Calendar className="h-4 w-4 text-pug-gold-700 dark:text-pug-gold-400" />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Hearings
        </h2>
        {canWrite && !adding && !blocked && (
          <button
            onClick={() => setAdding(true)}
            className="ml-auto flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-3.5 w-3.5" /> Add Hearing
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

      {adding && (
        <div className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-[rgb(var(--color-border))] p-3 md:grid-cols-2">
          <Field label="Hearing Date / Time">
            <input
              type="datetime-local"
              value={draft.hearing_date}
              onChange={(e) => setDraft({ ...draft, hearing_date: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Type">
            <select
              value={draft.hearing_type}
              onChange={(e) => setDraft({ ...draft, hearing_type: e.target.value })}
              className={inputCls}
            >
              {HEARING_TYPES.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Location">
            <input
              value={draft.location}
              onChange={(e) => setDraft({ ...draft, location: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label="Next Hearing Date / Time">
            <input
              type="datetime-local"
              value={draft.next_hearing_date}
              onChange={(e) => setDraft({ ...draft, next_hearing_date: e.target.value })}
              className={inputCls}
            />
          </Field>
          <div className="md:col-span-2">
            <Field label="Outcome / Notes">
              <textarea
                rows={3}
                value={draft.outcome}
                onChange={(e) => setDraft({ ...draft, outcome: e.target.value })}
                className={inputCls}
              />
            </Field>
          </div>
          <div className="md:col-span-2 flex gap-2">
            <button
              onClick={save}
              disabled={busy || !draft.hearing_date}
              className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> Save Hearing
            </button>
            <button
              onClick={() => setAdding(false)}
              className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="text-xs text-[rgb(var(--color-muted))]">No hearings recorded yet.</div>
      ) : (
        <ol className="divide-y divide-[rgb(var(--color-border))] rounded-md border border-[rgb(var(--color-border))]">
          {rows.map((h) => (
            <li key={h.id} className="px-4 py-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <div>
                  <span className="font-semibold">{h.hearing_type}</span>
                  <span className="ml-2 text-xs text-[rgb(var(--color-muted))]">
                    {new Date(h.hearing_date).toLocaleString()}
                    {h.location && ` - ${h.location}`}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-[rgb(var(--color-muted))]">
                  by {h.recorded_by_name}
                  {canWrite && (
                    <button
                      onClick={() => remove(h.id)}
                      className="rounded p-1 text-rose-600 hover:bg-rose-500/10"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
              {h.outcome && (
                <div className="mt-1 whitespace-pre-wrap rounded-md bg-[rgb(var(--color-border))]/20 px-3 py-2 text-xs">
                  {h.outcome}
                </div>
              )}
              {h.next_hearing_date && (
                <div className="mt-1 text-xs text-pug-gold-700 dark:text-pug-gold-400">
                  Next hearing: {new Date(h.next_hearing_date).toLocaleString()}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
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
