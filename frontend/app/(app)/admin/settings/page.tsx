'use client';

import { Save, Send, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Field = {
  key: string;
  label: string;
  type: string;
  default?: unknown;
  options?: string[];
  sensitive?: boolean;
  placeholder?: string;
  help?: string;
  env?: string;
};

type Group = {
  key: string;
  name: string;
  description: string;
  icon: string;
  actions?: string[];
  fields: Field[];
};

type GroupValues = Record<string, unknown> & { _meta?: Record<string, { source: string; has_value: boolean }> };

export default function SettingsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [active, setActive] = useState<string>('company');
  const [values, setValues] = useState<GroupValues>({});
  const [dirty, setDirty] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    api<Group[]>('/api/v1/settings/groups')
      .then((g) => setGroups(g))
      .catch((e) => setErr((e as ApiError).message));
  }, []);

  useEffect(() => {
    if (!active) return;
    setDirty({});
    setInfo(null);
    setErr(null);
    api<GroupValues>(`/api/v1/settings/groups/${active}`)
      .then(setValues)
      .catch((e) => setErr((e as ApiError).message));
  }, [active]);

  const currentGroup = groups.find((g) => g.key === active);

  function setField(key: string, v: unknown) {
    setValues((prev) => ({ ...prev, [key]: v }));
    setDirty((prev) => ({ ...prev, [key]: v }));
  }

  async function save() {
    if (Object.keys(dirty).length === 0) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const r = await api<GroupValues>(`/api/v1/settings/groups/${active}`, {
        method: 'PUT',
        body: { values: dirty },
      });
      setValues(r);
      setDirty({});
      setInfo(`Saved ${currentGroup?.name ?? active}.`);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function smtpTestSend() {
    const to = prompt('Send test email to:');
    if (!to) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const r = await api<{ ok: boolean; status: string; error: string }>(
        '/api/v1/settings/smtp/test-send',
        { method: 'POST', body: { to } },
      );
      if (r.ok) {
        setInfo(`Test sent. Status: ${r.status}.`);
      } else {
        setErr(`Test failed (${r.status}): ${r.error}`);
      }
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">System Settings</h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          DB-stored values override environment variables when set. Sensitive fields are
          encrypted at rest (AES-256-GCM) and masked in the UI.
        </p>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}
      {info && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
          {info}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[14rem_1fr]">
        {/* Tab list */}
        <nav className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-2 shadow-soft">
          <ul className="space-y-1">
            {groups.map((g) => (
              <li key={g.key}>
                <button
                  onClick={() => setActive(g.key)}
                  className={
                    'block w-full rounded-md px-3 py-2 text-left text-sm transition ' +
                    (active === g.key
                      ? 'bg-pug-gold-500/15 font-semibold text-pug-gold-700 dark:text-pug-gold-300'
                      : 'text-[rgb(var(--color-fg))] hover:bg-[rgb(var(--color-border))]/40')
                  }
                >
                  {g.name}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Group form */}
        <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
          {!currentGroup ? (
            <div className="text-sm text-[rgb(var(--color-muted))]">Loading...</div>
          ) : (
            <>
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">{currentGroup.name}</h2>
                  <p className="text-xs text-[rgb(var(--color-muted))]">
                    {currentGroup.description}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {currentGroup.actions?.includes('test_send') && (
                    <button
                      onClick={smtpTestSend}
                      disabled={busy}
                      className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-xs font-semibold hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-50"
                    >
                      <Send className="h-3.5 w-3.5" /> Test Send
                    </button>
                  )}
                  <button
                    onClick={save}
                    disabled={busy || Object.keys(dirty).length === 0}
                    className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-xs font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" /> Save
                    {Object.keys(dirty).length > 0 && ` (${Object.keys(dirty).length})`}
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {currentGroup.fields.map((f) => (
                  <FieldRow
                    key={f.key}
                    field={f}
                    value={values[f.key]}
                    source={values._meta?.[f.key]?.source}
                    onChange={(v) => setField(f.key, v)}
                  />
                ))}
              </div>

              {currentGroup.key === 'maintenance' && (
                <div className="mt-6 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
                  <AlertTriangle className="-mt-0.5 mr-1 inline h-4 w-4" />
                  Maintenance mode is currently advisory - the system continues to accept
                  writes. Enforcement will be wired in Phase 11+.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function FieldRow({
  field,
  value,
  source,
  onChange,
}: {
  field: Field;
  value: unknown;
  source?: string;
  onChange: (v: unknown) => void;
}) {
  const cls =
    'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

  return (
    <label className="block">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
          {field.label}
        </span>
        {field.sensitive && (
          <span className="rounded-full bg-pug-gold-500/15 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-300">
            Encrypted
          </span>
        )}
        {source && (
          <span className="text-[9px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
            from {source}
          </span>
        )}
      </div>
      {renderInput(field, value, onChange, cls)}
      {field.help && (
        <div className="mt-1 text-[10px] text-[rgb(var(--color-muted))]">{field.help}</div>
      )}
    </label>
  );
}

function renderInput(
  f: Field,
  value: unknown,
  onChange: (v: unknown) => void,
  cls: string,
) {
  switch (f.type) {
    case 'checkbox':
      return (
        <div className="flex items-center">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
            className="h-4 w-4"
          />
        </div>
      );
    case 'textarea':
      return (
        <textarea
          rows={3}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={f.placeholder}
          className={cls}
        />
      );
    case 'select':
      return (
        <select
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          className={cls}
        >
          {(f.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o === '' ? '(empty)' : o}
            </option>
          ))}
        </select>
      );
    case 'color':
      return (
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={String(value ?? '#000000')}
            onChange={(e) => onChange(e.target.value)}
            className="h-9 w-12 rounded border border-[rgb(var(--color-border))] bg-transparent"
          />
          <input
            value={String(value ?? '')}
            onChange={(e) => onChange(e.target.value)}
            placeholder="#c9a14a"
            className={cls}
          />
        </div>
      );
    case 'number':
      return (
        <input
          type="number"
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          placeholder={f.placeholder}
          className={cls}
        />
      );
    case 'password':
      return (
        <input
          type="password"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={f.placeholder ?? '********'}
          className={cls}
          autoComplete="new-password"
        />
      );
    case 'email':
      return (
        <input
          type="email"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={f.placeholder}
          className={cls}
        />
      );
    case 'url':
      return (
        <input
          type="url"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={f.placeholder}
          className={cls}
        />
      );
    case 'text':
    default:
      return (
        <input
          type="text"
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
          placeholder={f.placeholder}
          className={cls}
        />
      );
  }
}
