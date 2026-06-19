'use client';

import { Gavel, Save } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';

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
};

type Props = {
  caseId: number;
  status: string;
  onChange: () => void;
};

export function CourtFilingPanel({ caseId, status, onChange }: Props) {
  const me = useAuthStore((s) => s.me);
  const canFile = hasPermission(me, 'cases:file');
  const [filing, setFiling] = useState<Filing | null>(null);
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
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
  }, [caseId]);

  const blocked = status !== 'Approved' && status !== 'Filed';

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
      )}

      {!edit && !filing && !blocked && (
        <div className="text-xs text-[rgb(var(--color-muted))]">
          Click <strong>Record Filing</strong> to enter Police / Court case numbers.
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
            Tip: upload the govt acknowledgement via the <strong>Attachments</strong> section above
            after saving.
          </div>
        </div>
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

function Pair({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">{k}</div>
      <div className="text-sm">{v}</div>
    </div>
  );
}
