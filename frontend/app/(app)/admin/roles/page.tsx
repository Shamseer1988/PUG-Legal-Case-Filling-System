'use client';

import { useEffect, useState } from 'react';
import { Pencil, Save, X, Plus, Trash2 } from 'lucide-react';
import { api, ApiError } from '@/lib/api';

type Role = {
  id: number;
  name: string;
  description: string;
  permissions: string[];
  is_system: boolean;
};

const EMPTY = { name: '', description: '', permissions: [] as string[] };

export default function RolesPage() {
  const [rows, setRows] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Role | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(EMPTY);
  const [permsText, setPermsText] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      setRows(await api<Role[]>('/api/v1/roles'));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    reload();
  }, []);

  function startCreate() {
    setDraft(EMPTY);
    setPermsText('');
    setEditing(null);
    setCreating(true);
  }
  function startEdit(r: Role) {
    setDraft({ name: r.name, description: r.description, permissions: r.permissions });
    setPermsText(r.permissions.join('\n'));
    setEditing(r);
    setCreating(false);
  }
  function cancel() {
    setEditing(null);
    setCreating(false);
    setError(null);
  }

  async function save() {
    setError(null);
    const perms = permsText
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const body = { ...draft, permissions: perms };
      if (editing) {
        await api(`/api/v1/roles/${editing.id}`, { method: 'PATCH', body });
      } else {
        await api('/api/v1/roles', { method: 'POST', body });
      }
      cancel();
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  async function remove(id: number) {
    if (!confirm('Delete this role?')) return;
    try {
      await api(`/api/v1/roles/${id}`, { method: 'DELETE' });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const formOpen = creating || editing !== null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Roles &amp; Permissions</h1>
        {!formOpen && (
          <button
            onClick={startCreate}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-4 w-4" /> New Role
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {error}
        </div>
      )}

      {formOpen && (
        <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
          <div className="mb-3 text-sm font-semibold">
            {editing ? `Edit Role: ${editing.name}` : 'New Role'}
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Name
              </span>
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                disabled={!!editing?.is_system}
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Description
              </span>
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
              />
            </label>
          </div>
          <label className="mt-3 block">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
              Permissions (one per line; use <code>*</code> for full access)
            </span>
            <textarea
              rows={8}
              value={permsText}
              onChange={(e) => setPermsText(e.target.value)}
              className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 font-mono text-xs"
              placeholder={'cases:read\ncases:create\nmasters:read'}
            />
          </label>
          <div className="mt-4 flex gap-2">
            <button
              onClick={save}
              className="flex items-center gap-2 rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600"
            >
              <Save className="h-4 w-4" /> Save
            </button>
            <button
              onClick={cancel}
              className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
            >
              <X className="h-4 w-4" /> Cancel
            </button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
        <table className="w-full text-sm">
          <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Permissions</th>
              <th className="px-4 py-3">System</th>
              <th className="px-4 py-3 text-right">Actions</th>
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
                <td colSpan={5} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  No roles defined.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2 font-semibold">{r.name}</td>
                  <td className="px-4 py-2">{r.description}</td>
                  <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                    {r.permissions.slice(0, 4).join(', ')}
                    {r.permissions.length > 4 && ` +${r.permissions.length - 4}`}
                  </td>
                  <td className="px-4 py-2">
                    {r.is_system ? (
                      <span className="rounded-full bg-pug-gold-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-300">
                        System
                      </span>
                    ) : (
                      ''
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => startEdit(r)}
                      className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <Pencil className="h-3 w-3" /> Edit
                    </button>
                    {!r.is_system && (
                      <button
                        onClick={() => remove(r.id)}
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10"
                      >
                        <Trash2 className="h-3 w-3" /> Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
