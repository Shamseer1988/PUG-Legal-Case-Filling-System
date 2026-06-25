'use client';

import { ChevronDown, Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';

export type CaseSearchHit = {
  id: number;
  case_no: string;
  customer_name: string;
  division_name: string;
  legal_filing_amount: string;
  status: string;
};

type Props = {
  /** Selected case_no (the report param value). */
  value: string;
  onChange: (caseNo: string) => void;
  placeholder?: string;
  className?: string;
};

/** Typeahead picker for the reports' case_no parameter.
 *
 * Renders a table-style dropdown showing
 *   case_no | customer | division | amount
 * for each row, with role-scoped results served by
 * /api/v1/cases/search. Selecting a row writes the chosen case_no
 * back through onChange.
 */
export function CaseCombobox({ value, onChange, placeholder, className }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [rows, setRows] = useState<CaseSearchHit[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selectedLabel, setSelectedLabel] = useState<string>(value);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Resolve the label from the current value (so the closed combobox
  // shows "case_no - customer" instead of just the bare case number).
  useEffect(() => {
    if (!value) {
      setSelectedLabel('');
      return;
    }
    setSelectedLabel(value);
    // Fire and forget - if the case can't be resolved (e.g. user lost
    // access), the label falls back to the raw case_no.
    api<CaseSearchHit[]>(`/api/v1/cases/search?q=${encodeURIComponent(value)}&limit=5`)
      .then((hits) => {
        const exact = hits.find((h) => h.case_no === value);
        if (exact) setSelectedLabel(`${exact.case_no} - ${exact.customer_name}`);
      })
      .catch(() => undefined);
  }, [value]);

  const runSearch = useCallback(async (q: string) => {
    setLoading(true);
    try {
      const hits = await api<CaseSearchHit[]>(
        `/api/v1/cases/search?q=${encodeURIComponent(q)}&limit=25`,
      );
      setRows(hits);
      setActiveIdx(0);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounce search so we don't hammer the API on every keystroke
  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(() => runSearch(query), 200);
    return () => clearTimeout(handle);
  }, [query, open, runSearch]);

  // Click-outside closes the dropdown
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  function commit(row: CaseSearchHit) {
    onChange(row.case_no);
    setSelectedLabel(`${row.case_no} - ${row.customer_name}`);
    setOpen(false);
    setQuery('');
  }

  function clear() {
    onChange('');
    setSelectedLabel('');
    setQuery('');
    inputRef.current?.focus();
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, rows.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (rows[activeIdx]) commit(rows[activeIdx]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  const display = useMemo(() => selectedLabel || placeholder || 'Search by case number or customer...', [
    selectedLabel,
    placeholder,
  ]);

  return (
    <div ref={rootRef} className={`relative ${className ?? ''}`}>
      {/* Closed state: button-like trigger that opens the dropdown */}
      {!open && (
        <button
          type="button"
          onClick={() => {
            setOpen(true);
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
          className="flex w-full items-center gap-2 rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-left text-sm hover:border-pug-gold-500/60"
        >
          <Search className="h-4 w-4 shrink-0 text-[rgb(var(--color-muted))]" />
          <span
            className={`flex-1 truncate ${
              selectedLabel ? '' : 'text-[rgb(var(--color-muted))]'
            }`}
          >
            {display}
          </span>
          {selectedLabel && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                clear();
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  clear();
                }
              }}
              className="rounded p-0.5 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
              title="Clear"
            >
              <X className="h-3.5 w-3.5" />
            </span>
          )}
          <ChevronDown className="h-4 w-4 shrink-0 text-[rgb(var(--color-muted))]" />
        </button>
      )}

      {open && (
        <div
          className="absolute left-0 top-0 z-30 w-[min(900px,calc(100vw-2rem))] rounded-md border border-pug-gold-500/60 bg-[rgb(var(--color-card))] shadow-lg"
        >
          <div className="flex items-center gap-2 border-b border-[rgb(var(--color-border))] px-3 py-2">
            <Search className="h-4 w-4 text-[rgb(var(--color-muted))]" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKey}
              placeholder="Type to search..."
              className="flex-1 bg-transparent text-sm focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-0.5 text-[rgb(var(--color-muted))] hover:bg-[rgb(var(--color-border))]/40"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-[28rem] overflow-auto">
            {loading && (
              <div className="px-3 py-2 text-xs text-[rgb(var(--color-muted))]">
                Searching...
              </div>
            )}
            {!loading && rows.length === 0 && (
              <div className="px-3 py-2 text-xs text-[rgb(var(--color-muted))]">
                {query ? 'No cases match your search.' : 'Start typing to find a case.'}
              </div>
            )}
            {!loading && rows.length > 0 && (
              <table className="w-full table-auto text-xs">
                <thead className="sticky top-0 bg-[rgb(var(--color-border))]/30 text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                  <tr>
                    <th className="whitespace-nowrap px-3 py-2 text-left">Case No.</th>
                    <th className="whitespace-nowrap px-3 py-2 text-left">Customer</th>
                    <th className="whitespace-nowrap px-3 py-2 text-left">Division</th>
                    <th className="whitespace-nowrap px-3 py-2 text-right">Amount</th>
                    <th className="whitespace-nowrap px-3 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr
                      key={r.id}
                      onMouseEnter={() => setActiveIdx(i)}
                      onClick={() => commit(r)}
                      className={`cursor-pointer border-t border-[rgb(var(--color-border))] ${
                        i === activeIdx
                          ? 'bg-pug-gold-500/15'
                          : 'hover:bg-[rgb(var(--color-border))]/30'
                      }`}
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-mono">{r.case_no}</td>
                      <td className="whitespace-nowrap px-3 py-2">{r.customer_name || '-'}</td>
                      <td className="whitespace-nowrap px-3 py-2">{r.division_name || '-'}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                        {Number(r.legal_filing_amount).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">{r.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
