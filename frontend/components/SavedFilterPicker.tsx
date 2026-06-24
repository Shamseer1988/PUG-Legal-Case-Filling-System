'use client';

import {
  Bookmark,
  BookmarkPlus,
  ChevronDown,
  Lock,
  Trash2,
  Users,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';

export type SavedFilter = {
  id: number;
  name: string;
  report_key: string;
  params: Record<string, string>;
  is_public: boolean;
  is_mine: boolean;
  created_by_name: string;
};

type Props = {
  reportKey: string;
  /** Current parameter values - used as the body when the user
   *  clicks "Save as new filter". */
  currentParams: Record<string, string>;
  /** Replace the report's current parameter values with the picked
   *  filter's params. The caller is responsible for re-running. */
  onApply: (params: Record<string, string>) => void;
};

/** Saved-filter dropdown on the reports page (Phase 27).
 *
 *  Lets a user save the current parameter combo as a named filter
 *  and re-apply any of their saved filters (or any public filter
 *  shared by a teammate). The owner gets edit / delete affordances.
 */
export function SavedFilterPicker({ reportKey, currentParams, onApply }: Props) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<SavedFilter[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({ name: '', is_public: false });
  const [err, setErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api<SavedFilter[]>(
        `/api/v1/reports/saved?report_key=${encodeURIComponent(reportKey)}`,
      );
      setRows(list);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }, [reportKey]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, []);

  async function save() {
    setErr(null);
    try {
      const next = await api<SavedFilter>('/api/v1/reports/saved', {
        method: 'POST',
        body: {
          name: draft.name.trim(),
          report_key: reportKey,
          params: currentParams,
          is_public: draft.is_public,
        },
      });
      setRows((r) => [...r, next].sort((a, b) => a.name.localeCompare(b.name)));
      setCreating(false);
      setDraft({ name: '', is_public: false });
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Delete this saved filter?')) return;
    try {
      await api(`/api/v1/reports/saved/${id}`, { method: 'DELETE' });
      setRows((r) => r.filter((x) => x.id !== id));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
      >
        <Bookmark className="h-4 w-4" /> Saved filters
        <ChevronDown className="h-3.5 w-3.5 text-[rgb(var(--color-muted))]" />
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-30 w-80 max-w-[90vw] rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-xl">
          <div className="flex items-center justify-between border-b border-[rgb(var(--color-border))] px-3 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
              Saved filters
            </span>
            <button
              type="button"
              onClick={() => setCreating((c) => !c)}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] font-semibold text-pug-gold-700 hover:bg-pug-gold-500/10 dark:text-pug-gold-300"
            >
              <BookmarkPlus className="h-3.5 w-3.5" /> Save current
            </button>
          </div>

          {err && (
            <div className="m-2 rounded-md border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-xs text-rose-700 dark:text-rose-300">
              {err}
            </div>
          )}

          {creating && (
            <div className="space-y-2 border-b border-[rgb(var(--color-border))] p-3">
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="Filter name (e.g. Q2 Civil)"
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm focus:border-pug-gold-500 focus:outline-none"
              />
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={draft.is_public}
                  onChange={(e) =>
                    setDraft({ ...draft, is_public: e.target.checked })
                  }
                />
                Share with the team (public)
              </label>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setCreating(false);
                    setDraft({ name: '', is_public: false });
                  }}
                  className="rounded-md border border-[rgb(var(--color-border))] px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={save}
                  disabled={!draft.name.trim()}
                  className="rounded-md bg-pug-navy-700 px-2 py-1 text-xs font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </div>
          )}

          <div className="max-h-72 overflow-y-auto">
            {loading ? (
              <div className="px-3 py-3 text-xs text-[rgb(var(--color-muted))]">
                Loading...
              </div>
            ) : rows.length === 0 ? (
              <div className="px-3 py-3 text-xs text-[rgb(var(--color-muted))]">
                No saved filters yet. Configure the parameters above
                and click <strong>Save current</strong>.
              </div>
            ) : (
              <ul className="divide-y divide-[rgb(var(--color-border))]">
                {rows.map((row) => (
                  <li key={row.id} className="group flex items-center gap-2 px-3 py-2 text-sm">
                    <button
                      type="button"
                      onClick={() => {
                        onApply(row.params);
                        setOpen(false);
                      }}
                      className="flex flex-1 items-center gap-2 text-left"
                      title="Apply this filter"
                    >
                      {row.is_public ? (
                        <Users className="h-3.5 w-3.5 text-pug-gold-700 dark:text-pug-gold-400" />
                      ) : (
                        <Lock className="h-3.5 w-3.5 text-[rgb(var(--color-muted))]" />
                      )}
                      <span className="truncate font-medium">{row.name}</span>
                      {!row.is_mine && (
                        <span className="ml-auto text-[10px] text-[rgb(var(--color-muted))]">
                          {row.created_by_name}
                        </span>
                      )}
                    </button>
                    {row.is_mine && (
                      <button
                        type="button"
                        onClick={() => remove(row.id)}
                        title="Delete"
                        className="rounded p-1 text-rose-600 opacity-0 hover:bg-rose-500/10 group-hover:opacity-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
