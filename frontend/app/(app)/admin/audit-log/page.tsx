'use client';

import {
  ShieldCheck,
  ShieldAlert,
  Download,
  FileSpreadsheet,
  FileText,
  Key,
  Lock,
  RefreshCw,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { API_BASE, api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

type ListItem = {
  id: number;
  created_at: string;
  actor_id: number | null;
  actor_email: string;
  actor_role: string;
  ip_address: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  summary: string;
};

type Detail = ListItem & {
  user_agent: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  meta: Record<string, unknown>;
  prev_hash: string;
  row_hash: string;
};

type VerifyResult = {
  verified: boolean;
  count: number;
  issues: { id: number; issue: string }[];
  checked_at: string;
};

export default function AuditLogPage() {
  const token = useAuthStore((s) => s.accessToken);
  const [rows, setRows] = useState<ListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    action: '',
    entity_type: '',
    q: '',
    date_from: '',
    date_to: '',
  });
  const [selected, setSelected] = useState<Detail | null>(null);
  const [verify, setVerify] = useState<VerifyResult | null>(null);

  const qs = useMemo(() => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) {
      if (v) u.set(k, v);
    }
    return u.toString();
  }, [filters]);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api<ListItem[]>(`/api/v1/audit-log?${qs}&limit=300`);
      setRows(r);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qs]);

  async function openDetail(id: number) {
    try {
      const d = await api<Detail>(`/api/v1/audit-log/${id}`);
      setSelected(d);
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function runVerify() {
    try {
      setVerify(await api<VerifyResult>('/api/v1/audit-log/verify'));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function download(format: 'csv' | 'pdf' | 'signed.json') {
    const r = await fetch(`${API_BASE}/api/v1/audit-log.${format}?${qs}`, {
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
    a.download = `audit-log.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function showSigningKey() {
    try {
      const r = await api<{ public_key: string; format: string }>(
        '/api/v1/audit-log/signing-key',
      );
      // Surface as a copy-friendly alert dialog. A future iteration
      // can render this in a proper modal with a "Copy" button.
      window.prompt(
        `Public key (${r.format}). Hand this to your external auditor `
          + 'so they can verify any later signed export. Cmd/Ctrl-C to copy:',
        r.public_key,
      );
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Audit Log</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Append-only trail with SHA-256 hash chain. Click any row for the before / after diff.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={runVerify}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <ShieldCheck className="h-4 w-4" /> Verify Chain
          </button>
          <button
            onClick={() => download('csv')}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <FileSpreadsheet className="h-4 w-4" /> CSV
          </button>
          <button
            onClick={() => download('pdf')}
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <FileText className="h-4 w-4" /> PDF
          </button>
          <button
            onClick={() => download('signed.json')}
            title="Tamper-evident JSON export signed with Ed25519"
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <Lock className="h-4 w-4" /> Signed JSON
          </button>
          <button
            onClick={showSigningKey}
            title="Get the Ed25519 public key for offline verification"
            className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
          >
            <Key className="h-4 w-4" /> Signing Key
          </button>
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>
      </div>

      {verify && (
        <div
          className={
            'rounded-xl border px-4 py-3 text-sm ' +
            (verify.verified
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
              : 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300')
          }
        >
          <div className="flex items-center gap-2 font-semibold">
            {verify.verified ? (
              <ShieldCheck className="h-4 w-4" />
            ) : (
              <ShieldAlert className="h-4 w-4" />
            )}
            {verify.verified
              ? `Chain verified across ${verify.count} entries.`
              : `Tampering detected (${verify.issues.length} issue(s) over ${verify.count} entries).`}
            <button
              onClick={() => setVerify(null)}
              className="ml-auto rounded p-1 hover:bg-white/20"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
          {!verify.verified && (
            <ul className="mt-1 text-xs">
              {verify.issues.slice(0, 10).map((i) => (
                <li key={`${i.id}-${i.issue}`}>
                  Entry #{i.id}: {i.issue}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
        <Field label="Action">
          <input
            value={filters.action}
            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            placeholder="e.g. login, update"
            className={cls}
          />
        </Field>
        <Field label="Entity">
          <input
            value={filters.entity_type}
            onChange={(e) => setFilters({ ...filters, entity_type: e.target.value })}
            placeholder="e.g. Case, Bank"
            className={cls}
          />
        </Field>
        <Field label="From">
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
            className={cls}
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
            className={cls}
          />
        </Field>
        <Field label="Search">
          <input
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            placeholder="summary / actor / entity"
            className={cls}
          />
        </Field>
        <button
          onClick={() => setFilters({ action: '', entity_type: '', q: '', date_from: '', date_to: '' })}
          className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
        >
          Clear
        </button>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft lg:col-span-2">
          <table className="w-full text-sm">
            <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">Action</th>
                <th className="px-4 py-2">Entity</th>
                <th className="px-4 py-2">Actor</th>
                <th className="px-4 py-2">Summary</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                    Loading...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-[rgb(var(--color-muted))]">
                    No entries match these filters.
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => openDetail(r.id)}
                    className={
                      'cursor-pointer border-t border-[rgb(var(--color-border))] hover:bg-[rgb(var(--color-border))]/30 ' +
                      (selected?.id === r.id ? 'bg-pug-gold-500/10' : '')
                    }
                  >
                    <td className="px-4 py-2 text-xs">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-xs">
                      <ActionPill action={r.action} />
                    </td>
                    <td className="px-4 py-2 text-xs">
                      {r.entity_type}
                      {r.entity_id !== null ? ` #${r.entity_id}` : ''}
                    </td>
                    <td className="px-4 py-2 text-xs">{r.actor_email || '-'}</td>
                    <td className="px-4 py-2 text-xs">{r.summary}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
          {!selected ? (
            <div className="text-sm text-[rgb(var(--color-muted))]">
              Click an entry to see the full detail and diff.
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <ActionPill action={selected.action} />
                  <div className="mt-1 font-semibold">{selected.summary}</div>
                  <div className="text-xs text-[rgb(var(--color-muted))]">
                    {selected.entity_type}
                    {selected.entity_id !== null ? ` #${selected.entity_id}` : ''} &middot;{' '}
                    {new Date(selected.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="rounded p-1 hover:bg-[rgb(var(--color-border))]/40"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <Pair k="Actor" v={`${selected.actor_email || '-'} (${selected.actor_role || '-'})`} />
              <Pair k="IP" v={selected.ip_address || '-'} />
              <Pair k="User-Agent" v={selected.user_agent || '-'} />
              <Pair k="Row Hash" v={selected.row_hash} mono />
              <Pair k="Prev Hash" v={selected.prev_hash || '(genesis)'} mono />
              <Diff before={selected.before} after={selected.after} />
              {Object.keys(selected.meta).length > 0 && (
                <details className="rounded border border-[rgb(var(--color-border))] p-2">
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
                    Metadata
                  </summary>
                  <pre className="mt-2 overflow-auto text-[10px]">
                    {JSON.stringify(selected.meta, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const cls =
  'rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col">
      <span className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}

function Pair({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">{k}</div>
      <div className={'break-all text-xs ' + (mono ? 'font-mono' : '')}>{v}</div>
    </div>
  );
}

function Diff({
  before,
  after,
}: {
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}) {
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})]));
  if (keys.length === 0) return null;
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
        Diff
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <th className="px-2 py-1">Field</th>
            <th className="px-2 py-1">Before</th>
            <th className="px-2 py-1">After</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className="border-t border-[rgb(var(--color-border))]">
              <td className="px-2 py-1 font-semibold">{k}</td>
              <td className="px-2 py-1 text-rose-700 dark:text-rose-300">
                {formatVal(before[k])}
              </td>
              <td className="px-2 py-1 text-emerald-700 dark:text-emerald-300">
                {formatVal(after[k])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function ActionPill({ action }: { action: string }) {
  const cls =
    {
      create: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40',
      update: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/40',
      delete: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40',
      login: 'bg-pug-gold-500/15 text-pug-gold-700 dark:text-pug-gold-300 border-pug-gold-500/40',
      login_failed: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40',
    }[action] ?? 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/40';
  return (
    <span
      className={
        'inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
        cls
      }
    >
      {action.replace(/_/g, ' ')}
    </span>
  );
}
