'use client';

import {
  AlertTriangle,
  Archive,
  Cloud,
  Database,
  Download,
  HardDrive,
  Plug,
  RefreshCw,
  Save,
  ShieldAlert,
  Trash2,
  Undo2,
  Upload,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

// --------------- types ---------------
type Job = {
  id: number;
  kind: string;
  status: string;
  format: string;
  storage_path: string;
  sidecar_path: string;
  cloud_path: string;
  size_bytes: number;
  attachment_count: number;
  finished_at: string | null;
  created_at: string;
  notes: string;
};

type Status = {
  backup_count: number;
  last_backup_at: string | null;
  total_size_bytes: number;
  folder: string;
  folder_writable: boolean;
  free_space_bytes: number;
};

type Activity = {
  id: number;
  occurred_at: string;
  activity_type: string;
  status: string;
  file_name: string;
  cloud_key: string;
  message: string;
};

type R2Item = {
  key: string;
  name: string;
  size: number;
  last_modified: string | null;
};

type R2Test = {
  ok: boolean;
  message: string;
  bucket?: string | null;
  prefix?: string | null;
  endpoint?: string | null;
};

type BackupSettings = {
  daily_enabled: boolean;
  daily_time: string;
  weekly_enabled: boolean;
  weekly_day: string;
  weekly_time: string;
  local_folder: string;
  cloud_provider: string;
  cloud_folder: string;
};

const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

// --------------- page ---------------
export default function BackupsPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [rows, setRows] = useState<Job[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [r2, setR2] = useState<R2Item[]>([]);
  const [r2Test, setR2Test] = useState<R2Test | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<BackupSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [restoreFor, setRestoreFor] = useState<{ job?: Job; r2Key?: string } | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [takeSnapshot, setTakeSnapshot] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setErr(null);
    try {
      const [list, st, act, r2list] = await Promise.all([
        api<Job[]>('/api/v1/backups'),
        api<Status>('/api/v1/backups/status'),
        api<Activity[]>('/api/v1/backups/activity'),
        api<R2Item[]>('/api/v1/backups/r2').catch(() => []),
      ]);
      setRows(list);
      setStatus(st);
      setActivity(act);
      setR2(r2list);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function loadSettings() {
    try {
      const s = await api<BackupSettings>('/api/v1/backups/settings');
      setSettings(s);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    load();
    loadSettings();
  }, []);

  async function saveSettings() {
    if (!settings) return;
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const s = await api<BackupSettings>('/api/v1/backups/settings', {
        method: 'PUT',
        body: settings,
      });
      setSettings(s);
      setInfo('Backup settings saved.');
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function createBackup(pushCloud: boolean) {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const j = await api<Job>('/api/v1/backups', {
        method: 'POST',
        body: { notes: '', push_cloud: pushCloud },
      });
      setInfo(
        `Backup #${j.id} created (${formatBytes(j.size_bytes)})${
          pushCloud ? ' and pushed to cloud.' : '.'
        }`,
      );
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function testR2() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api<R2Test>('/api/v1/backups/r2/test', { method: 'POST' });
      setR2Test(r);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function downloadBackup(j: Job) {
    const r = await fetch(`${API_BASE}/api/v1/backups/${j.id}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    if (!r.ok) {
      setErr(`Download failed (${r.status})`);
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = j.storage_path;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function deleteBackup(j: Job) {
    if (!confirm(`Delete backup file ${j.storage_path}? This cannot be undone.`)) return;
    try {
      await api(`/api/v1/backups/${j.id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function performRestore() {
    if (!restoreFor) return;
    if (confirmation !== 'RESTORE') {
      setErr('Type RESTORE to confirm.');
      return;
    }
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      if (restoreFor.r2Key) {
        await api(`/api/v1/backups/r2/restore`, {
          method: 'POST',
          body: {
            key: restoreFor.r2Key,
            confirmation,
            take_safety_snapshot: takeSnapshot,
          },
        });
      } else if (restoreFor.job) {
        await api(`/api/v1/backups/${restoreFor.job.id}/restore`, {
          method: 'POST',
          body: { confirmation, take_safety_snapshot: takeSnapshot },
        });
      }
      setInfo('Restore complete.');
      setRestoreFor(null);
      setConfirmation('');
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadAndRestore(file: File) {
    if (!confirm(
      `Upload ${file.name} and restore the database from it? ` +
        `A safety snapshot will be taken first. Type RESTORE in the confirmation modal next.`,
    )) {
      return;
    }
    const conf = prompt('Type RESTORE to confirm:');
    if (conf !== 'RESTORE') {
      setErr('Restore cancelled.');
      return;
    }
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const url = `${API_BASE}/api/v1/backups/upload-restore?confirmation=RESTORE&take_safety_snapshot=true`;
      const r = await fetch(url, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: fd,
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(body.detail || `Upload failed (${r.status})`);
      }
      setInfo(`Restored from ${file.name}.`);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Backup &amp; Restore</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Postgres <code>.dump</code> snapshots; optional Cloudflare R2 off-site copy.
            Same format as PUG Finance App backups.
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
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

      {/* ------ Backup settings card ------ */}
      {settings && (
        <Card title="Backup settings" subtitle="Schedule, destination and cloud copy for automatic database backups.">
          <div className="mb-3 flex justify-end">
            <button
              onClick={saveSettings}
              disabled={busy}
              className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> Save changes
            </button>
          </div>

          <Row title="Daily backup" hint="Run an automatic local backup every day at the time you set.">
            <div className="flex items-center gap-3">
              <Toggle
                checked={settings.daily_enabled}
                onChange={(v) => setSettings({ ...settings, daily_enabled: v })}
                label="Enabled"
              />
              <Field label="Daily time">
                <input
                  type="time"
                  value={settings.daily_time}
                  onChange={(e) => setSettings({ ...settings, daily_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
            </div>
          </Row>

          <Row
            title="Weekly cloud backup"
            hint="Once a week, also copy the backup to your cloud / external folder."
          >
            <div className="flex flex-wrap items-center gap-3">
              <Toggle
                checked={settings.weekly_enabled}
                onChange={(v) => setSettings({ ...settings, weekly_enabled: v })}
                label="Enabled"
              />
              <Field label="Week day">
                <select
                  value={settings.weekly_day}
                  onChange={(e) => setSettings({ ...settings, weekly_day: e.target.value })}
                  className={inputCls}
                >
                  {WEEKDAYS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Weekly time">
                <input
                  type="time"
                  value={settings.weekly_time}
                  onChange={(e) => setSettings({ ...settings, weekly_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
            </div>
          </Row>

          <Row
            title="Local backup folder"
            hint={
              <>
                Absolute path where <code>pg_dump</code> <code>.dump</code> files are written.
                Leave empty to use the <code>BACKUP_FOLDER</code> env var.
              </>
            }
          >
            <input
              value={settings.local_folder}
              onChange={(e) => setSettings({ ...settings, local_folder: e.target.value })}
              placeholder="e.g. /var/lib/pug/backups"
              className={inputCls}
            />
          </Row>

          <Row
            title="Cloud / external destination"
            hint="Optional. Used by the weekly cloud backup and the &quot;Backup now + cloud&quot; action."
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Field label="Cloud provider">
                <select
                  value={settings.cloud_provider}
                  onChange={(e) => setSettings({ ...settings, cloud_provider: e.target.value })}
                  className={inputCls}
                >
                  <option value="">(none)</option>
                  <option value="cloudflare_r2">Cloudflare R2</option>
                </select>
              </Field>
              <Field label="Cloud / external folder">
                <input
                  value={settings.cloud_folder}
                  onChange={(e) => setSettings({ ...settings, cloud_folder: e.target.value })}
                  placeholder="s3://my-bucket/legal-backups"
                  className={inputCls}
                />
              </Field>
            </div>
          </Row>
        </Card>
      )}

      {/* ------ R2 panel ------ */}
      <Card
        title={
          <>
            <Cloud className="inline h-4 w-4" /> Cloudflare R2 — off-site cloud backups
          </>
        }
        subtitle="The weekly job and &quot;Backup now + cloud&quot; upload .dump files here."
      >
        <div className="mb-3">
          <button
            onClick={testR2}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <Plug className="h-4 w-4" /> Test R2 connection
          </button>
          {r2Test && (
            <div
              className={
                'mt-2 rounded-md border px-3 py-2 text-xs ' +
                (r2Test.ok
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                  : 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300')
              }
            >
              {r2Test.message}
              {r2Test.ok && r2Test.bucket && (
                <span className="ml-2">
                  · bucket=<code>{r2Test.bucket}</code> prefix=<code>{r2Test.prefix || '(root)'}</code>
                </span>
              )}
            </div>
          )}
        </div>

        <Table
          head={['Backup file (R2)', 'Size', 'Modified', 'Action']}
          alignRight={[3]}
          empty="No R2 backups found (or R2 not configured)."
        >
          {r2.map((o) => (
            <tr key={o.key} className="border-t border-[rgb(var(--color-border))]">
              <td className="px-4 py-2 font-mono text-xs">{o.name}</td>
              <td className="px-4 py-2 tabular-nums">{formatBytes(o.size)}</td>
              <td className="px-4 py-2 text-xs">
                {o.last_modified ? new Date(o.last_modified).toLocaleString() : '-'}
              </td>
              <td className="px-4 py-2 text-right">
                <button
                  onClick={() => {
                    setRestoreFor({ r2Key: o.key });
                    setConfirmation('');
                  }}
                  className="inline-flex items-center gap-1 rounded border border-pug-gold-500/40 bg-pug-gold-500/10 px-2 py-1 text-[11px] font-semibold text-pug-gold-700 hover:bg-pug-gold-500/20"
                >
                  <Undo2 className="h-3 w-3" /> Restore
                </button>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {/* ------ Local files + actions ------ */}
      <Card title={<><Database className="inline h-4 w-4" /> Backup files</>} subtitle={
        status ? (
          <>
            Database snapshots in <code>{status.folder}</code>. The scheduled backup runs based on
            the settings above.
          </>
        ) : null
      }>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-1.5 text-sm hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-50"
          >
            <Upload className="h-4 w-4" /> Upload + restore
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".dump"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadAndRestore(f);
            }}
          />
          <button
            onClick={() => createBackup(false)}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-1.5 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
          >
            <Archive className="h-4 w-4" /> Backup now
          </button>
          <button
            onClick={() => createBackup(true)}
            disabled={busy}
            className="flex items-center gap-2 rounded-md border border-pug-gold-500/40 px-3 py-1.5 text-sm hover:bg-pug-gold-500/10 disabled:opacity-50"
          >
            <Cloud className="h-4 w-4" /> Backup now + cloud
          </button>
        </div>

        {status && (
          <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              label="Folder"
              value={status.folder.split('/').pop() || status.folder}
              icon={<HardDrive className="h-4 w-4" />}
              border="emerald"
            />
            <Stat
              label="Writable"
              value={status.folder_writable ? 'yes' : 'no'}
              icon={null}
              border={status.folder_writable ? 'emerald' : 'rose'}
            />
            <Stat
              label="Free space"
              value={formatBytes(status.free_space_bytes)}
              icon={null}
              border="sky"
            />
            <Stat
              label="Backup count"
              value={String(status.backup_count)}
              icon={null}
              border="amber"
            />
          </div>
        )}

        <Table
          head={['File', 'Created', 'Size', 'Actions']}
          alignRight={[3]}
          empty="No backups yet. Click Backup now to create your first one."
        >
          {rows.map((j) => (
            <tr key={j.id} className="border-t border-[rgb(var(--color-border))]">
              <td className="px-4 py-2 font-mono text-xs">
                {j.storage_path}
                {j.format === 'legacy_enc' && (
                  <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                    LEGACY
                  </span>
                )}
                {j.cloud_path && (
                  <div className="text-[10px] text-[rgb(var(--color-muted))]">
                    <Cloud className="inline h-3 w-3" /> {j.cloud_path}
                  </div>
                )}
              </td>
              <td className="px-4 py-2 text-xs">
                {new Date(j.finished_at || j.created_at).toLocaleString()}
              </td>
              <td className="px-4 py-2 tabular-nums">{formatBytes(j.size_bytes)}</td>
              <td className="px-4 py-2 text-right">
                <button
                  onClick={() => downloadBackup(j)}
                  className="mr-1 inline-flex items-center gap-1 rounded border border-[rgb(var(--color-border))] px-2 py-1 text-[11px] hover:bg-[rgb(var(--color-border))]/40"
                >
                  <Download className="h-3 w-3" /> Download
                </button>
                {j.format === 'legacy_enc' ? (
                  <span
                    title="Legacy .bkp.enc restore is disabled. Download the file and convert offline if you really need it."
                    className="mr-1 inline-flex cursor-not-allowed items-center gap-1 rounded border border-[rgb(var(--color-border))]/40 px-2 py-1 text-[11px] text-[rgb(var(--color-muted))]"
                  >
                    <Undo2 className="h-3 w-3" /> Restore (archive)
                  </span>
                ) : (
                  <button
                    onClick={() => {
                      setRestoreFor({ job: j });
                      setConfirmation('');
                    }}
                    className="mr-1 inline-flex items-center gap-1 rounded border border-pug-gold-500/40 bg-pug-gold-500/10 px-2 py-1 text-[11px] font-semibold text-pug-gold-700 hover:bg-pug-gold-500/20"
                  >
                    <Undo2 className="h-3 w-3" /> Restore
                  </button>
                )}
                <button
                  onClick={() => deleteBackup(j)}
                  className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-rose-600 hover:bg-rose-500/10"
                >
                  <Trash2 className="h-3 w-3" /> Delete
                </button>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      {/* ------ Activity log ------ */}
      <Card title="Backup activity log" subtitle={null}>
        <Table
          head={['Date', 'Type', 'Status', 'File', 'Cloud', 'Message']}
          alignRight={[]}
          empty="No activity yet."
        >
          {activity.map((a) => (
            <tr key={a.id} className="border-t border-[rgb(var(--color-border))]">
              <td className="px-4 py-2 text-xs">{new Date(a.occurred_at).toLocaleString()}</td>
              <td className="px-4 py-2 text-xs">{a.activity_type}</td>
              <td className="px-4 py-2 text-xs">
                <span
                  className={
                    'rounded px-2 py-0.5 text-[10px] font-bold uppercase ' +
                    (a.status === 'Success'
                      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                      : 'bg-rose-500/15 text-rose-700 dark:text-rose-300')
                  }
                >
                  {a.status}
                </span>
              </td>
              <td className="px-4 py-2 font-mono text-[10px]">{a.file_name || '-'}</td>
              <td className="px-4 py-2 font-mono text-[10px]">{a.cloud_key || '-'}</td>
              <td className="px-4 py-2 text-xs">{a.message}</td>
            </tr>
          ))}
        </Table>
      </Card>

      {restoreFor && (
        <RestoreModal
          target={restoreFor}
          confirmation={confirmation}
          setConfirmation={setConfirmation}
          takeSnapshot={takeSnapshot}
          setTakeSnapshot={setTakeSnapshot}
          busy={busy}
          onCancel={() => {
            setRestoreFor(null);
            setConfirmation('');
          }}
          onConfirm={performRestore}
        />
      )}
    </div>
  );
}

// --------------- small UI primitives ---------------
function Card({
  title,
  subtitle,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
      <div className="mb-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[rgb(var(--color-muted))]">{subtitle}</p>
        )}
      </div>
      {children}
    </div>
  );
}

function Row({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-3 grid grid-cols-1 gap-3 border-t border-[rgb(var(--color-border))] pt-3 md:grid-cols-[260px_1fr]">
      <div>
        <div className="text-xs font-semibold">{title}</div>
        {hint && (
          <div className="mt-0.5 text-[10px] text-[rgb(var(--color-muted))]">{hint}</div>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={
        'flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ' +
        (checked
          ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
          : 'bg-[rgb(var(--color-border))]/30 text-[rgb(var(--color-muted))]')
      }
    >
      <span
        className={
          'inline-block h-3 w-3 rounded-full ' +
          (checked ? 'bg-emerald-500' : 'bg-[rgb(var(--color-muted))]/60')
        }
      />
      {label}
    </button>
  );
}

function Stat({
  label,
  value,
  icon,
  border,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  border: 'emerald' | 'rose' | 'sky' | 'amber';
}) {
  const borderCls = {
    emerald: 'border-t-4 border-t-emerald-500',
    rose: 'border-t-4 border-t-rose-500',
    sky: 'border-t-4 border-t-sky-500',
    amber: 'border-t-4 border-t-amber-500',
  }[border];
  return (
    <div className={`${borderCls} rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft`}>
      <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
        {icon}
      </div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}

function Table({
  head,
  alignRight,
  empty,
  children,
}: {
  head: string[];
  alignRight: number[];
  empty: string;
  children: React.ReactNode;
}) {
  const rows = Array.isArray(children) ? children : [children];
  return (
    <div className="overflow-hidden rounded-md border border-[rgb(var(--color-border))]">
      <table className="w-full text-sm">
        <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
          <tr>
            {head.map((h, i) => (
              <th
                key={h}
                className={'px-4 py-2 ' + (alignRight.includes(i) ? 'text-right' : '')}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.flat().filter(Boolean).length === 0 ? (
            <tr>
              <td colSpan={head.length} className="px-4 py-8 text-center text-[rgb(var(--color-muted))]">
                {empty}
              </td>
            </tr>
          ) : (
            children
          )}
        </tbody>
      </table>
    </div>
  );
}

function RestoreModal({
  target,
  confirmation,
  setConfirmation,
  takeSnapshot,
  setTakeSnapshot,
  busy,
  onCancel,
  onConfirm,
}: {
  target: { job?: Job; r2Key?: string };
  confirmation: string;
  setConfirmation: (v: string) => void;
  takeSnapshot: boolean;
  setTakeSnapshot: (v: boolean) => void;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const label = target.r2Key
    ? `R2 object ${target.r2Key}`
    : `backup #${target.job?.id} (${target.job?.storage_path})`;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-rose-500/40 bg-[rgb(var(--color-card))] p-6 shadow-2xl">
        <div className="flex items-center gap-2 text-rose-700 dark:text-rose-300">
          <ShieldAlert className="h-5 w-5" />
          <h2 className="text-lg font-bold">Restore from {label}</h2>
        </div>
        <p className="mt-3 text-sm">
          This will <strong>wipe the database</strong> and replace it with the contents of {label}.
          Attachments are also replaced from the sidecar file (if present).
        </p>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={takeSnapshot}
            onChange={(e) => setTakeSnapshot(e.target.checked)}
            className="h-4 w-4"
          />
          Take a <strong>safety snapshot</strong> first (recommended)
        </label>
        <label className="mt-3 block text-sm">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
            Type <code className="font-mono text-rose-600">RESTORE</code> to confirm
          </span>
          <input
            autoFocus
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            className="w-full rounded-md border border-rose-500/40 bg-transparent px-3 py-2 font-mono text-sm focus:border-rose-500 focus:outline-none"
          />
        </label>
        <div className="mt-4 flex gap-2">
          <button
            onClick={onConfirm}
            disabled={busy || confirmation !== 'RESTORE'}
            className="flex items-center gap-2 rounded-md bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
          >
            <Undo2 className="h-4 w-4" /> Restore Now
          </button>
          <button
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-[rgb(var(--color-border))] px-4 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}
