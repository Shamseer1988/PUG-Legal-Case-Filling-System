'use client';

import { Save, Send, AlertTriangle, CheckCircle2, Upload } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError, API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

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
      const r = await api<{
        email_log_id: number;
        status: string;
        error: string;
        sent_at: string | null;
      }>('/api/v1/admin/email-log/test', {
        method: 'POST',
        body: { to_email: to },
      });
      if (r.status === 'Sent') {
        setInfo(
          r.error
            ? `Test sent in console mode (no SMTP host configured). Email log #${r.email_log_id}.`
            : `Test sent successfully. Email log #${r.email_log_id}.`,
        );
      } else {
        // Status Queued/Failed -- surface the SMTP error so the
        // admin can fix the config without scrolling logs.
        setErr(
          `Test ${r.status} (email log #${r.email_log_id}): ${r.error || 'no error reported'}`,
        );
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
    case 'image':
      return (
        <ImageUploadRow
          field={f}
          value={String(value ?? '')}
          onChange={onChange}
        />
      );
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

function ImageUploadRow({
  field,
  value,
  onChange,
}: {
  field: Field;
  value: string;
  onChange: (v: string) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const token = useAuthStore((s) => s.accessToken);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setHasError(false);
  }, [value]);

  const uploadType = field.key.includes('favicon') ? 'favicon' : 'logo';

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];

    const allowedExtensions =
      uploadType === 'favicon'
        ? ['.ico', '.png', '.jpg', '.jpeg', '.gif']
        : ['.png', '.jpg', '.jpeg', '.webp', '.svg'];
    const fileExt = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.includes(fileExt)) {
      setUploadErr(`Invalid extension. Allowed: ${allowedExtensions.join(', ')}`);
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setUploadErr('File too large. Max size is 2MB.');
      return;
    }

    setUploading(true);
    setUploadErr(null);
    try {
      const fd = new FormData();
      fd.append('file', file);

      const res = await fetch(`${API_BASE}/api/v1/settings/upload?type=${uploadType}`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: fd,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Upload failed');
      }

      const data = await res.json();
      onChange(data.url);
    } catch (err) {
      setUploadErr((err as Error).message);
    } finally {
      setUploading(false);
    }
  }

  const previewUrl = value
    ? value.startsWith('http')
      ? value
      : `${API_BASE}${value}`
    : uploadType === 'favicon'
    ? `${API_BASE}/api/v1/settings/public/favicon`
    : `${API_BASE}/api/v1/settings/public/logo`;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-4 rounded-md border border-[rgb(var(--color-border))] p-3">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-[rgb(var(--color-border))]/20 border border-[rgb(var(--color-border))] overflow-hidden">
          {hasError ? (
            <div className="text-[10px] text-[rgb(var(--color-muted))] text-center">No preview</div>
          ) : (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={previewUrl}
              alt={field.label}
              className="max-h-full max-w-full object-contain"
              onError={() => setHasError(true)}
            />
          )}
        </div>

        <div className="flex-1 space-y-1">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-pug-navy-700 hover:bg-pug-navy-600 px-3 py-1.5 text-xs font-semibold text-white transition disabled:opacity-50">
            <Upload className="h-3.5 w-3.5" />
            {uploading ? 'Uploading...' : 'Upload Image'}
            <input
              type="file"
              accept={uploadType === 'favicon' ? '.ico,.png,.jpg,.jpeg,.gif' : 'image/*'}
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
            />
          </label>
          <div className="text-[10px] text-[rgb(var(--color-muted))] truncate max-w-[200px]">
            {value ? 'Uploaded custom asset' : 'Using default template asset'}
          </div>
        </div>
      </div>
      {uploadErr && <div className="text-xs text-rose-500">{uploadErr}</div>}
    </div>
  );
}
