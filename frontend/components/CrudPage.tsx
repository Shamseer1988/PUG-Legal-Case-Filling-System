'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2, Pencil, X, Save } from 'lucide-react';
import { api, ApiError } from '@/lib/api';

export type CrudField =
  | { name: string; label: string; type?: 'text' | 'email' | 'number'; required?: boolean; readOnly?: boolean }
  | {
      name: string;
      label: string;
      type: 'select';
      options: { value: string | number; label: string }[];
      required?: boolean;
      allowEmpty?: boolean;
    }
  | { name: string; label: string; type: 'checkbox' };

type Row = Record<string, unknown> & { id: number };

type Props = {
  title: string;
  resource: string; // e.g. "/api/v1/masters/divisions"
  fields: CrudField[];
  columns: { key: string; label: string; render?: (v: unknown, row: Row) => React.ReactNode }[];
  emptyTemplate: Record<string, unknown>;
  canWrite?: boolean;
};

export function CrudPage({
  title,
  resource,
  fields,
  columns,
  emptyTemplate,
  canWrite = true,
}: Props) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Row | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<Record<string, unknown>>(emptyTemplate);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<Row[]>(resource);
      setRows(data);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => {
    reload();
  }, [reload]);

  function startCreate() {
    setDraft(emptyTemplate);
    setEditing(null);
    setCreating(true);
    setError(null);
  }
  function startEdit(row: Row) {
    setDraft({ ...row });
    setEditing(row);
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
        const id = editing.id;
        const diff: Record<string, unknown> = {};
        for (const k of Object.keys(draft)) {
          if (draft[k] !== editing[k]) diff[k] = draft[k];
        }
        await api(`${resource}/${id}`, { method: 'PATCH', body: diff });
      } else {
        await api(resource, { method: 'POST', body: draft });
      }
      cancel();
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Delete this record?')) return;
    try {
      await api(`${resource}/${id}`, { method: 'DELETE' });
      reload();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  const formOpen = creating || editing !== null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{title}</h1>
        {canWrite && !formOpen && (
          <button
            onClick={startCreate}
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-4 w-4" /> New
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
            {editing ? `Edit ${title.slice(0, -1)} #${editing.id}` : `New ${title.slice(0, -1)}`}
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {fields.map((f) => (
              <FieldInput key={f.name} field={f} draft={draft} setDraft={setDraft} />
            ))}
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
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-3">
                  {c.label}
                </th>
              ))}
              {canWrite && <th className="px-4 py-3 text-right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length + 1} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  Loading...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 1} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                  No records yet.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-2">
                      {c.render ? c.render(r[c.key], r) : String(r[c.key] ?? '')}
                    </td>
                  ))}
                  {canWrite && (
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => startEdit(r)}
                        className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                      >
                        <Pencil className="h-3 w-3" /> Edit
                      </button>
                      <button
                        onClick={() => remove(r.id)}
                        className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-rose-600 hover:bg-rose-500/10"
                      >
                        <Trash2 className="h-3 w-3" /> Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FieldInput({
  field,
  draft,
  setDraft,
}: {
  field: CrudField;
  draft: Record<string, unknown>;
  setDraft: (d: Record<string, unknown>) => void;
}) {
  const value = draft[field.name];
  const onChange = (v: unknown) => setDraft({ ...draft, [field.name]: v });

  if (field.type === 'checkbox') {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4"
        />
        {field.label}
      </label>
    );
  }

  if (field.type === 'select') {
    return (
      <label className="block">
        <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
          {field.label}
        </span>
        <select
          required={field.required}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === '') onChange(null);
            else if (typeof field.options[0]?.value === 'number') onChange(Number(raw));
            else onChange(raw);
          }}
          className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm"
        >
          {field.allowEmpty && <option value="">--</option>}
          {field.options.map((o) => (
            <option key={String(o.value)} value={String(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {field.label}
      </span>
      <input
        type={field.type ?? 'text'}
        required={field.required}
        readOnly={field.readOnly}
        value={value === null || value === undefined ? '' : String(value)}
        onChange={(e) => {
          const t = e.target.value;
          if (field.type === 'number') onChange(t === '' ? null : Number(t));
          else onChange(t);
        }}
        className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
      />
    </label>
  );
}
