'use client';

import { useEffect, useState } from 'react';
import { Plus, Trash2, Pencil, X, Save } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { useMasterOptions } from '@/lib/useMasters';

type User = {
  id: number;
  email: string;
  full_name: string;
  role_id: number;
  role_name: string;
  is_active: boolean;
  is_super: boolean;
  division_ids: number[];
};

type Role = { id: number; name: string };

type Draft = {
  email: string;
  full_name: string;
  password: string;
  role_id: number | null;
  is_active: boolean;
  is_super: boolean;
  division_ids: number[];
};

const EMPTY: Draft = {
  email: '',
  full_name: '',
  password: '',
  role_id: null,
  is_active: true,
  is_super: false,
  division_ids: [],
};

export default function UsersPage() {
  const [rows, setRows] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<User | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');

  async function reload() {
    setLoading(true);
    try {
      const [users, allRoles] = await Promise.all([
        api<User[]>('/api/v1/users'),
        api<Role[]>('/api/v1/roles'),
      ]);
      setRows(users);
      setRoles(allRoles);
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
    setDraft({ ...EMPTY, role_id: roles[0]?.id ?? null });
    setEditing(null);
    setCreating(true);
    setError(null);
  }
  function startEdit(u: User) {
    setDraft({
      email: u.email,
      full_name: u.full_name,
      password: '',
      role_id: u.role_id,
      is_active: u.is_active,
      is_super: u.is_super,
      division_ids: u.division_ids,
    });
    setEditing(u);
    setCreating(false);
    setError(null);
  }
  function cancel() {
    setEditing(null);
    setCreating(false);
    setError(null);
  }

  async function save() {
    setError(null);
    try {
      if (editing) {
        const body: Record<string, unknown> = {
          full_name: draft.full_name,
          role_id: draft.role_id,
          is_active: draft.is_active,
          is_super: draft.is_super,
          division_ids: draft.division_ids,
        };
        if (draft.password) body.password = draft.password;
        await api(`/api/v1/users/${editing.id}`, { method: 'PATCH', body });
      } else {
        await api('/api/v1/users', { method: 'POST', body: draft });
      }
      cancel();
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Delete this user?')) return;
    try {
      await api(`/api/v1/users/${id}`, { method: 'DELETE' });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const formOpen = creating || editing !== null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Users</h1>
        {!formOpen && (
          <button
            onClick={startCreate}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-4 w-4" /> New User
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
            {editing ? `Edit User #${editing.id}` : 'New User'}
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Labeled label="Email">
              <input
                type="email"
                required
                disabled={!!editing}
                value={draft.email}
                onChange={(e) => setDraft({ ...draft, email: e.target.value })}
                className={inputCls}
              />
            </Labeled>
            <Labeled label="Full Name">
              <input
                required
                value={draft.full_name}
                onChange={(e) => setDraft({ ...draft, full_name: e.target.value })}
                className={inputCls}
              />
            </Labeled>
            <Labeled label={editing ? 'Password (leave blank to keep)' : 'Password'}>
              <input
                type="password"
                required={!editing}
                value={draft.password}
                onChange={(e) => setDraft({ ...draft, password: e.target.value })}
                className={inputCls}
              />
            </Labeled>
            <Labeled label="Role">
              <select
                required
                value={draft.role_id ?? ''}
                onChange={(e) => setDraft({ ...draft, role_id: Number(e.target.value) })}
                className={inputCls}
              >
                <option value="" disabled>
                  Select role
                </option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </Labeled>
            <Labeled label="Divisions">
              <select
                multiple
                value={draft.division_ids.map(String)}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    division_ids: Array.from(e.target.selectedOptions).map((o) =>
                      Number(o.value),
                    ),
                  })
                }
                className={inputCls + ' min-h-[6rem]'}
              >
                {divisions.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </Labeled>
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                  className="h-4 w-4"
                />
                Active
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.is_super}
                  onChange={(e) => setDraft({ ...draft, is_super: e.target.checked })}
                  className="h-4 w-4"
                />
                Super user (bypass all permissions)
              </label>
            </div>
          </div>

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
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Active</th>
              <th className="px-4 py-3">Super</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  Loading...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  No users yet.
                </td>
              </tr>
            ) : (
              rows.map((u) => (
                <tr key={u.id} className="border-t border-[rgb(var(--color-border))]">
                  <td className="px-4 py-2">{u.email}</td>
                  <td className="px-4 py-2">{u.full_name}</td>
                  <td className="px-4 py-2">{u.role_name}</td>
                  <td className="px-4 py-2">{u.is_active ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-2">{u.is_super ? 'Yes' : 'No'}</td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => startEdit(u)}
                      className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                    >
                      <Pencil className="h-3 w-3" /> Edit
                    </button>
                    <button
                      onClick={() => remove(u.id)}
                      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10"
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
    </div>
  );
}

const inputCls =
  'w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none';

function Labeled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      {children}
    </label>
  );
}
