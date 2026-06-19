'use client';

import { Save, X, Play, Pause, Trash2, Clock, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type ReportDescriptor = {
  key: string;
  name: string;
  description: string;
  params: { name: string; type: string; label: string; options: string[] | null }[];
};

type Schedule = {
  id: number;
  name: string;
  report_key: string;
  params: Record<string, string>;
  cron: string;
  recipients: string[];
  cc: string[];
  bcc: string[];
  formats: string[];
  notes: string;
  is_active: boolean;
  last_run_at: string | null;
  last_run_status: string;
  last_run_error: string;
  next_run_at: string | null;
};

type Run = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  rows_count: number;
  error: string;
  email_log_id: number | null;
};

type Draft = {
  name: string;
  report_key: string;
  params: Record<string, string>;
  cron: string;
  recipients: string;
  cc: string;
  bcc: string;
  formats: { pdf: boolean; xlsx: boolean };
  notes: string;
};

const PRESETS: { label: string; cron: string }[] = [
  { label: 'Every weekday at 9:00 UTC', cron: '0 9 * * 1-5' },
  { label: 'Every Monday at 9:00 UTC', cron: '0 9 * * 1' },
  { label: '1st of month at 9:00 UTC', cron: '0 9 1 * *' },
  { label: 'Daily at 18:00 UTC', cron: '0 18 * * *' },
  { label: 'Hourly (test)', cron: '0 * * * *' },
];

const EMPTY: Draft = {
  name: '',
  report_key: '',
  params: {},
  cron: '0 9 * * 1',
  recipients: '',
  cc: '',
  bcc: '',
  formats: { pdf: true, xlsx: false },
  notes: '',
};

export function ScheduleForm({ scheduleId }: { scheduleId?: number }) {
  const router = useRouter();
  const isEdit = scheduleId !== undefined;
  const [descriptors, setDescriptors] = useState<ReportDescriptor[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [meta, setMeta] = useState<Schedule | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    api<ReportDescriptor[]>('/api/v1/reports')
      .then((rs) => {
        setDescriptors(rs);
        setDraft((d) => (d.report_key ? d : { ...d, report_key: rs[0]?.key ?? '' }));
      })
      .catch((e) => setErr((e as ApiError).message));
  }, []);

  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const [s, runs] = await Promise.all([
          api<Schedule>(`/api/v1/scheduled-reports/${scheduleId}`),
          api<Run[]>(`/api/v1/scheduled-reports/${scheduleId}/history`),
        ]);
        setMeta(s);
        setHistory(runs);
        setDraft({
          name: s.name,
          report_key: s.report_key,
          params: s.params || {},
          cron: s.cron,
          recipients: s.recipients.join(', '),
          cc: s.cc.join(', '),
          bcc: s.bcc.join(', '),
          formats: {
            pdf: s.formats.includes('pdf'),
            xlsx: s.formats.includes('xlsx'),
          },
          notes: s.notes,
        });
      } catch (e) {
        setErr((e as ApiError).message);
      }
    })();
  }, [scheduleId, isEdit]);

  const currentReport = descriptors.find((d) => d.key === draft.report_key);

  function toPayload(): Record<string, unknown> {
    const formats: string[] = [];
    if (draft.formats.pdf) formats.push('pdf');
    if (draft.formats.xlsx) formats.push('xlsx');
    return {
      name: draft.name,
      report_key: draft.report_key,
      params: draft.params,
      cron: draft.cron,
      recipients: splitList(draft.recipients),
      cc: splitList(draft.cc),
      bcc: splitList(draft.bcc),
      formats: formats.length ? formats : ['pdf'],
      notes: draft.notes,
    };
  }

  async function save(thenRun = false) {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      let id = scheduleId;
      if (id) {
        await api(`/api/v1/scheduled-reports/${id}`, { method: 'PATCH', body: toPayload() });
      } else {
        const created = await api<Schedule>('/api/v1/scheduled-reports', {
          method: 'POST',
          body: toPayload(),
        });
        id = created.id;
      }
      if (thenRun) {
        await api(`/api/v1/scheduled-reports/${id}/run-now`, { method: 'POST' });
        setInfo('Schedule saved and run kicked off.');
      } else {
        setInfo('Schedule saved.');
      }
      router.push(`/schedules/${id}`);
      router.refresh();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function pauseResume() {
    if (!meta) return;
    try {
      await api(
        `/api/v1/scheduled-reports/${meta.id}/${meta.is_active ? 'pause' : 'resume'}`,
        { method: 'POST' },
      );
      router.refresh();
      setMeta({ ...meta, is_active: !meta.is_active });
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function remove() {
    if (!meta) return;
    if (!confirm(`Delete schedule "${meta.name}"?`)) return;
    try {
      await api(`/api/v1/scheduled-reports/${meta.id}`, { method: 'DELETE' });
      router.push('/schedules');
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">
          {isEdit ? 'Edit Schedule' : 'New Schedule'}
        </h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Cron times run in UTC. Recipients receive a branded email with attachments.
        </p>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          {info}
        </div>
      )}

      <div className="space-y-4 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label="Name" required>
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className={cls}
            />
          </Field>
          <Field label="Report" required>
            <select
              value={draft.report_key}
              onChange={(e) => setDraft({ ...draft, report_key: e.target.value, params: {} })}
              className={cls}
            >
              {descriptors.map((d) => (
                <option key={d.key} value={d.key}>
                  {d.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {currentReport && currentReport.params.length > 0 && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
              Report Parameters
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {currentReport.params.map((p) => (
                <Field key={p.name} label={p.label}>
                  {p.type === 'select' ? (
                    <select
                      value={draft.params[p.name] ?? ''}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          params: { ...draft.params, [p.name]: e.target.value },
                        })
                      }
                      className={cls}
                    >
                      {(p.options ?? []).map((o) => (
                        <option key={o} value={o}>
                          {o || 'All'}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={p.type === 'date' ? 'date' : 'text'}
                      value={draft.params[p.name] ?? ''}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          params: { ...draft.params, [p.name]: e.target.value },
                        })
                      }
                      className={cls}
                    />
                  )}
                </Field>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            Cadence (UTC)
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Field label="Cron Expression" required>
              <input
                value={draft.cron}
                onChange={(e) => setDraft({ ...draft, cron: e.target.value })}
                placeholder="0 9 * * 1"
                className={cls + ' font-mono'}
              />
            </Field>
            <Field label="Presets">
              <select
                value=""
                onChange={(e) => e.target.value && setDraft({ ...draft, cron: e.target.value })}
                className={cls}
              >
                <option value="">-- pick a preset --</option>
                {PRESETS.map((p) => (
                  <option key={p.cron} value={p.cron}>
                    {p.label} ({p.cron})
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <p className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">
            Standard 5-field cron: <code>minute hour day-of-month month day-of-week</code>.
          </p>
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            Recipients
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Field label="To (comma-separated)" required>
              <input
                value={draft.recipients}
                onChange={(e) => setDraft({ ...draft, recipients: e.target.value })}
                placeholder="cfo@pug.local, fm@pug.local"
                className={cls}
              />
            </Field>
            <Field label="CC">
              <input
                value={draft.cc}
                onChange={(e) => setDraft({ ...draft, cc: e.target.value })}
                className={cls}
              />
            </Field>
            <Field label="BCC">
              <input
                value={draft.bcc}
                onChange={(e) => setDraft({ ...draft, bcc: e.target.value })}
                className={cls}
              />
            </Field>
          </div>
          <div className="mt-3 flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={draft.formats.pdf}
                onChange={(e) =>
                  setDraft({ ...draft, formats: { ...draft.formats, pdf: e.target.checked } })
                }
                className="h-4 w-4"
              />
              PDF
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={draft.formats.xlsx}
                onChange={(e) =>
                  setDraft({ ...draft, formats: { ...draft.formats, xlsx: e.target.checked } })
                }
                className="h-4 w-4"
              />
              Excel
            </label>
          </div>
        </div>

        <Field label="Notes (shown in the email)">
          <textarea
            rows={2}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            className={cls}
          />
        </Field>

        <div className="flex flex-wrap gap-2 border-t border-[rgb(var(--color-border))] pt-3">
          <button
            onClick={() => save(false)}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-4 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
          >
            <Save className="h-4 w-4" /> Save
          </button>
          <button
            onClick={() => save(true)}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-4 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
          >
            <Play className="h-4 w-4" /> Save &amp; Run Now
          </button>
          {isEdit && meta && (
            <>
              <button
                onClick={pauseResume}
                className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-4 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
              >
                {meta.is_active ? (
                  <>
                    <Pause className="h-4 w-4" /> Pause
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" /> Resume
                  </>
                )}
              </button>
              <button
                onClick={remove}
                className="ml-auto flex items-center gap-2 rounded-md border border-rose-500/40 px-4 py-2 text-sm text-rose-600 hover:bg-rose-500/10"
              >
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            </>
          )}
        </div>
      </div>

      {isEdit && meta && (
        <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            Status
          </h2>
          <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Active
              </div>
              <div>{meta.is_active ? 'Yes' : 'Paused'}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Next Run (UTC)
              </div>
              <div className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3 text-[rgb(var(--color-muted))]" />
                {meta.next_run_at ? new Date(meta.next_run_at).toLocaleString() : '-'}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Last Run
              </div>
              <div>
                {meta.last_run_at ? (
                  <span
                    className={
                      meta.last_run_status === 'Success'
                        ? 'inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300'
                        : 'inline-flex items-center gap-1 text-rose-700 dark:text-rose-300'
                    }
                  >
                    {meta.last_run_status === 'Success' ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <AlertTriangle className="h-3 w-3" />
                    )}
                    {meta.last_run_status} - {new Date(meta.last_run_at).toLocaleString()}
                  </span>
                ) : (
                  <span className="text-[rgb(var(--color-muted))]">Never</span>
                )}
              </div>
            </div>
          </dl>
          {meta.last_run_error && (
            <div className="mt-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-700 dark:text-rose-300">
              {meta.last_run_error}
            </div>
          )}
        </section>
      )}

      {isEdit && history.length > 0 && (
        <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
          <div className="border-b border-[rgb(var(--color-border))] px-4 py-3 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            Run History
          </div>
          <table className="w-full text-sm">
            <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
              <tr>
                <th className="px-4 py-2">Started</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Rows</th>
                <th className="px-4 py-2">Email Log</th>
                <th className="px-4 py-2">Error</th>
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2 text-xs">{new Date(r.started_at).toLocaleString()}</td>
                  <td className="px-4 py-2 text-xs">
                    <span
                      className={
                        r.status === 'Success'
                          ? 'rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:text-emerald-300'
                          : 'rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold text-rose-700 dark:text-rose-300'
                      }
                    >
                      {r.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{r.rows_count}</td>
                  <td className="px-4 py-2 text-xs">{r.email_log_id ?? '-'}</td>
                  <td className="px-4 py-2 text-xs text-rose-600">{r.error || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

const cls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
        {required && <span className="ml-1 text-rose-500">*</span>}
      </span>
      {children}
    </label>
  );
}

function splitList(s: string): string[] {
  return s
    .split(/[\s,;]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}
