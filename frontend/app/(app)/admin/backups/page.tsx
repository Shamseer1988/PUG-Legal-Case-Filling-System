'use client';

import {
  Archive,
  Download,
  HardDrive,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Undo2,
  Unlock,
  X,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

type Job = {
  id: number;
  kind: string;
  status: string;
  storage_path: string;
  size_bytes: number;
  checksum_sha256: string;
  is_encrypted: boolean;
  attachment_count: number;
  table_row_counts: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
  error: string;
  notes: string;
  created_at: string;
};

type Status = {
  encryption_enabled: boolean;
  backup_count: number;
  last_backup_at: string | null;
  total_size_bytes: number;
};

type VerifyResult = {
  ok: boolean;
  message: string;
  checksum_sha256?: string;
  actual_sha256?: string;
  expected_sha256?: string;
  entries?: number;
};

type RestoreJob = {
  id: number;
  status: string;
  tables_restored: number;
  rows_restored: number;
  safety_snapshot_id: number | null;
  error: string;
};

const KIND_LABEL: Record<string, string> = {
  manual: 'Manual',
  scheduled: 'Scheduled',
  safety_snapshot: 'Safety Snapshot',
};

export default function BackupsPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [rows, setRows] = useState<Job[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [verify, setVerify] = useState<{ id: number; result: VerifyResult } | null>(null);
  const [restoreFor, setRestoreFor] = useState<Job | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [takeSnapshot, setTakeSnapshot] = useState(true);
  const [notes, setNotes] = useState('');

  async function load() {
    setErr(null);
    try {
      const [list, st] = await Promise.all([
        api<Job[]>('/api/v1/backups'),
        api<Status>('/api/v1/backups/status'),
      ]);
      setRows(list);
      setStatus(st);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function createBackup() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const j = await api<Job>('/api/v1/backups', { method: 'POST', body: { notes } });
      setInfo(`Backup #${j.id} created (${formatBytes(j.size_bytes)}).`);
      setNotes('');
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function verifyBackup(j: Job) {
    try {
      const r = await api<VerifyResult>(`/api/v1/backups/${j.id}/verify`);
      setVerify({ id: j.id, result: r });
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function deleteBackup(j: Job) {
    if (!confirm(`Delete backup #${j.id}? The file and DB record will be removed.`)) return;
    try {
      await api(`/api/v1/backups/${j.id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      setErr((e as ApiError).message);
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
      const rj = await api<RestoreJob>(`/api/v1/backups/${restoreFor.id}/restore`, {
        method: 'POST',
        body: { confirmation, take_safety_snapshot: takeSnapshot },
      });
      setInfo(
        `Restored ${rj.tables_restored} tables / ${rj.rows_restored} rows. ` +
          (rj.safety_snapshot_id
            ? `Pre-restore snapshot saved as #${rj.safety_snapshot_id}.`
            : ''),
      );
      setRestoreFor(null);
      setConfirmation('');
      load();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Backup &amp; Restore</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Encrypted snapshots of every table + the attachments tree. Same engine as PugFin.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </div>

      {status && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat
            label="Backups"
            value={String(status.backup_count)}
            icon={<Archive className="h-4 w-4" />}
          />
          <Stat
            label="Total Size"
            value={formatBytes(status.total_size_bytes)}
            icon={<HardDrive className="h-4 w-4" />}
          />
          <Stat
            label="Last Backup"
            value={
              status.last_backup_at ? new Date(status.last_backup_at).toLocaleString() : 'Never'
            }
            icon={<Archive className="h-4 w-4" />}
          />
          <Stat
            label="Encryption"
            value={status.encryption_enabled ? 'AES-256-GCM' : 'Disabled'}
            icon={
              status.encryption_enabled ? (
                <Lock className="h-4 w-4 text-emerald-600" />
              ) : (
                <Unlock className="h-4 w-4 text-rose-600" />
              )
            }
          />
        </div>
      )}

      <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
              Notes (optional)
            </span>
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. pre-deployment snapshot"
              className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
            />
          </label>
          <button
            onClick={createBackup}
            disabled={busy}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-4 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
          >
            <Archive className="h-4 w-4" /> Create Backup
          </button>
        </div>
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

      {verify && (
        <div
          className={
            'rounded-xl border px-4 py-3 text-sm ' +
            (verify.result.ok
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
              : 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300')
          }
        >
          <div className="flex items-center gap-2 font-semibold">
            {verify.result.ok ? (
              <ShieldCheck className="h-4 w-4" />
            ) : (
              <ShieldAlert className="h-4 w-4" />
            )}
            Backup #{verify.id}: {verify.result.message}
            <button
              onClick={() => setVerify(null)}
              className="ml-auto rounded p-1 hover:bg-white/20"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <table className="w-full text-sm">
          <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <tr>
              <th className="px-4 py-2">ID</th>
              <th className="px-4 py-2">Kind</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Size</th>
              <th className="px-4 py-2">Enc.</th>
              <th className="px-4 py-2">Files</th>
              <th className="px-4 py-2">Created</th>
              <th className="px-4 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-[rgb(var(--color-muted))]">
                  No backups yet. Click <strong>Create Backup</strong> to start.
                </td>
              </tr>
            ) : (
              rows.map((j) => (
                <tr key={j.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2 font-mono text-xs">#{j.id}</td>
                  <td className="px-4 py-2 text-xs">
                    {KIND_LABEL[j.kind] ?? j.kind}
                    {j.notes && (
                      <div className="text-[10px] text-[rgb(var(--color-muted))]">{j.notes}</div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    <StatusPill s={j.status} />
                  </td>
                  <td className="px-4 py-2 tabular-nums">{formatBytes(j.size_bytes)}</td>
                  <td className="px-4 py-2">
                    {j.is_encrypted ? (
                      <Lock className="h-3.5 w-3.5 text-emerald-600" />
                    ) : (
                      <Unlock className="h-3.5 w-3.5 text-rose-600" />
                    )}
                  </td>
                  <td className="px-4 py-2 tabular-nums">{j.attachment_count}</td>
                  <td className="px-4 py-2 text-xs">
                    {new Date(j.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => verifyBackup(j)}
                      className="mr-1 inline-flex items-center gap-1 rounded border border-[rgb(var(--color-border))] px-2 py-1 text-[11px] hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <ShieldCheck className="h-3 w-3" /> Verify
                    </button>
                    <button
                      onClick={() => downloadBackup(j)}
                      className="mr-1 inline-flex items-center gap-1 rounded border border-[rgb(var(--color-border))] px-2 py-1 text-[11px] hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <Download className="h-3 w-3" /> Download
                    </button>
                    <button
                      onClick={() => setRestoreFor(j)}
                      className="mr-1 inline-flex items-center gap-1 rounded bg-pug-gold-500 px-2 py-1 text-[11px] font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
                    >
                      <Undo2 className="h-3 w-3" /> Restore
                    </button>
                    <button
                      onClick={() => deleteBackup(j)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-rose-600 hover:bg-rose-500/10"
                    >
                      <Trash2 className="h-3 w-3" /> Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {restoreFor && (
        <RestoreModal
          job={restoreFor}
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

function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
          {label}
        </div>
        {icon}
      </div>
      <div className="mt-1 text-lg font-bold">{value}</div>
    </div>
  );
}

function StatusPill({ s }: { s: string }) {
  const cls =
    s === 'Completed'
      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40'
      : s === 'Failed'
        ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40'
        : 'bg-pug-gold-500/15 text-pug-gold-700 dark:text-pug-gold-300 border-pug-gold-500/40';
  return (
    <span
      className={
        'inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
        cls
      }
    >
      {s}
    </span>
  );
}

function RestoreModal({
  job,
  confirmation,
  setConfirmation,
  takeSnapshot,
  setTakeSnapshot,
  busy,
  onCancel,
  onConfirm,
}: {
  job: Job;
  confirmation: string;
  setConfirmation: (v: string) => void;
  takeSnapshot: boolean;
  setTakeSnapshot: (v: boolean) => void;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-xl border border-rose-500/40 bg-[rgb(var(--color-card))] p-6 shadow-2xl">
        <div className="flex items-center gap-2 text-rose-700 dark:text-rose-300">
          <ShieldAlert className="h-5 w-5" />
          <h2 className="text-lg font-bold">Restore from Backup #{job.id}</h2>
        </div>
        <p className="mt-3 text-sm">
          This will <strong>wipe every table</strong> and replace it with the contents of backup
          #{job.id} ({formatBytes(job.size_bytes)}). All attachments will also be replaced.
        </p>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={takeSnapshot}
            onChange={(e) => setTakeSnapshot(e.target.checked)}
            className="h-4 w-4"
          />
          Take a <strong>safety snapshot</strong> of the current state first (recommended)
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
