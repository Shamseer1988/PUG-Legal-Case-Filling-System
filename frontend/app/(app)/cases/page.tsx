'use client';

import Link from 'next/link';
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Filter,
  Plus,
  Printer,
  Search,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';

type Row = {
  id: number;
  case_no: string;
  customer_id: number;
  customer_name: string;
  customer_code: string;
  division_id: number;
  division_name: string;
  status: string;
  current_stage: string;
  legal_filing_amount: string;
  is_criminal: boolean;
  is_civil: boolean;
  created_at: string;
  submitted_at: string | null;
  sla_due_at: string | null;
};

type Page = {
  items: Row[];
  total: number;
  limit: number;
  offset: number;
};

const STATUS_COLOR: Record<string, string> = {
  Draft: 'bg-slate-500/15 text-slate-700 border-slate-500/40 dark:text-slate-300',
  Submitted: 'bg-pug-gold-500/20 text-pug-gold-700 border-pug-gold-500/40 dark:text-pug-gold-300',
  'In Review': 'bg-blue-500/15 text-blue-700 border-blue-500/40 dark:text-blue-300',
  'Clarification Requested':
    'bg-amber-500/15 text-amber-700 border-amber-500/40 dark:text-amber-300',
  Approved: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/40 dark:text-emerald-300',
  Filed: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/40 dark:text-emerald-300',
  'Lawyer Approved': 'bg-emerald-500/15 text-emerald-700 border-emerald-500/40 dark:text-emerald-300',
  Rejected: 'bg-rose-500/15 text-rose-700 border-rose-500/40 dark:text-rose-300',
  Closed: 'bg-slate-700/30 text-slate-700 border-slate-700/40 dark:text-slate-200',
};

const ALL_STATUSES = [
  'Draft',
  'Submitted',
  'In Review',
  'Clarification Requested',
  'Approved',
  'Filed',
  'Lawyer Approved',
  'Rejected',
  'Closed',
];

const ALL_STAGES = [
  'Accountant',
  'Sales Manager',
  'Division Manager',
  'Audit',
  'Finance Manager',
  'Executive Director',
  'Chairman / MD',
  'Lawyer',
  'Closed',
];

const PAGE_SIZE = 25;

export default function CasesListPage() {
  const me = useAuthStore((s) => s.me);
  const divisions = useMasterOptions('/api/v1/masters/divisions');
  const [page, setPage] = useState<Page>({ items: [], total: 0, limit: 0, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Filter state (held in component memory, applied on debounce)
  const [q, setQ] = useState('');
  const [statusIn, setStatusIn] = useState<Set<string>>(new Set());
  const [stageIn, setStageIn] = useState<Set<string>>(new Set());
  const [divisionIn, setDivisionIn] = useState<Set<number>>(new Set());
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [caseType, setCaseType] = useState<'all' | 'criminal' | 'civil'>('all');
  const [offset, setOffset] = useState(0);

  const buildQuery = useCallback(() => {
    const u = new URLSearchParams();
    if (q.trim()) u.set('q', q.trim());
    for (const s of statusIn) u.append('status_in', s);
    for (const s of stageIn) u.append('stage_in', s);
    for (const d of divisionIn) u.append('division_id_in', String(d));
    if (amountMin) u.set('amount_min', amountMin);
    if (amountMax) u.set('amount_max', amountMax);
    if (dateFrom) u.set('date_from', dateFrom);
    if (dateTo) u.set('date_to', dateTo);
    if (caseType === 'criminal') u.set('is_criminal', 'true');
    if (caseType === 'civil') u.set('is_civil', 'true');
    u.set('limit', String(PAGE_SIZE));
    u.set('offset', String(offset));
    return u.toString();
  }, [q, statusIn, stageIn, divisionIn, amountMin, amountMax, dateFrom, dateTo, caseType, offset]);

  // Debounce search so a typing user doesn't fire one request per keystroke
  useEffect(() => {
    let cancelled = false;
    const id = setTimeout(async () => {
      setLoading(true);
      setErr(null);
      try {
        const data = await api<Page>(`/api/v1/cases/search-full?${buildQuery()}`);
        if (!cancelled) setPage(data);
      } catch (e) {
        if (!cancelled) setErr((e as ApiError).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [buildQuery]);

  // Whenever a filter changes, jump back to page 1 so the user
  // doesn't see "no results" on what is actually page 4 of nothing.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setOffset(0), [q, statusIn, stageIn, divisionIn, amountMin, amountMax, dateFrom, dateTo, caseType]);

  function clearAll() {
    setQ('');
    setStatusIn(new Set());
    setStageIn(new Set());
    setDivisionIn(new Set());
    setAmountMin('');
    setAmountMax('');
    setDateFrom('');
    setDateTo('');
    setCaseType('all');
    setOffset(0);
  }

  const activeFilterCount =
    (q ? 1 : 0) +
    statusIn.size +
    stageIn.size +
    divisionIn.size +
    (amountMin ? 1 : 0) +
    (amountMax ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0) +
    (caseType !== 'all' ? 1 : 0);

  const hasNext = offset + PAGE_SIZE < page.total;
  const hasPrev = offset > 0;
  const fromIndex = page.items.length === 0 ? 0 : offset + 1;
  const toIndex = offset + page.items.length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Cases</h1>
        {hasPermission(me, 'cases:create') && (
          <Link
            href="/cases/new"
            className="flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
          >
            <Plus className="h-4 w-4" /> New Case
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_1fr]">
        {/* ---------- Filter sidebar ---------- */}
        <aside className="space-y-4 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
              <Filter className="h-4 w-4" /> Filters
              {activeFilterCount > 0 && (
                <span className="rounded-full bg-pug-gold-500/20 px-2 py-0.5 text-[10px] font-bold text-pug-gold-700 dark:text-pug-gold-300">
                  {activeFilterCount}
                </span>
              )}
            </div>
            {activeFilterCount > 0 && (
              <button
                onClick={clearAll}
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-rose-600 hover:bg-rose-500/10"
              >
                <X className="h-3 w-3" /> Clear
              </button>
            )}
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[rgb(var(--color-muted))]" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search case no / customer / notes"
              className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent py-1.5 pl-7 pr-2 text-sm focus:border-pug-gold-500 focus:outline-none"
            />
          </div>

          {/* Status checkboxes */}
          <FilterGroup title="Status">
            {ALL_STATUSES.map((s) => (
              <CheckRow
                key={s}
                checked={statusIn.has(s)}
                onChange={() => toggle(statusIn, setStatusIn, s)}
                label={s}
              />
            ))}
          </FilterGroup>

          {/* Stage checkboxes */}
          <FilterGroup title="Stage">
            {ALL_STAGES.map((s) => (
              <CheckRow
                key={s}
                checked={stageIn.has(s)}
                onChange={() => toggle(stageIn, setStageIn, s)}
                label={s}
              />
            ))}
          </FilterGroup>

          {/* Division multi-select */}
          {divisions.length > 0 && (
            <FilterGroup title="Division">
              {divisions.map((d) => (
                <CheckRow
                  key={d.value}
                  checked={divisionIn.has(d.value)}
                  onChange={() => toggle(divisionIn, setDivisionIn, d.value)}
                  label={d.label}
                />
              ))}
            </FilterGroup>
          )}

          {/* Case type radio */}
          <FilterGroup title="Case Type">
            {[
              { v: 'all', label: 'All' },
              { v: 'criminal', label: 'Criminal' },
              { v: 'civil', label: 'Civil' },
            ].map((opt) => (
              <label key={opt.v} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="case-type"
                  checked={caseType === opt.v}
                  onChange={() => setCaseType(opt.v as typeof caseType)}
                />
                {opt.label}
              </label>
            ))}
          </FilterGroup>

          {/* Amount range */}
          <FilterGroup title="Legal Amount">
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                inputMode="decimal"
                placeholder="Min"
                value={amountMin}
                onChange={(e) => setAmountMin(e.target.value)}
                className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm text-right tabular-nums focus:border-pug-gold-500 focus:outline-none"
              />
              <input
                type="number"
                inputMode="decimal"
                placeholder="Max"
                value={amountMax}
                onChange={(e) => setAmountMax(e.target.value)}
                className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm text-right tabular-nums focus:border-pug-gold-500 focus:outline-none"
              />
            </div>
          </FilterGroup>

          {/* Date range */}
          <FilterGroup title="Created Between">
            <div className="grid grid-cols-2 gap-2">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm focus:border-pug-gold-500 focus:outline-none"
              />
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm focus:border-pug-gold-500 focus:outline-none"
              />
            </div>
          </FilterGroup>
        </aside>

        {/* ---------- Results panel ---------- */}
        <div className="space-y-3">
          {err && (
            <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
              {err}
            </div>
          )}

          <div className="flex items-center justify-between text-xs text-[rgb(var(--color-muted))]">
            <div>
              {loading
                ? 'Searching...'
                : `Showing ${fromIndex}-${toIndex} of ${page.total}`}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                disabled={!hasPrev || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded border border-[rgb(var(--color-border))] hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-40"
                aria-label="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setOffset((o) => o + PAGE_SIZE)}
                disabled={!hasNext || loading}
                className="inline-flex h-7 w-7 items-center justify-center rounded border border-[rgb(var(--color-border))] hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-40"
                aria-label="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft">
            <table className="w-full text-sm">
              <thead className="bg-[rgb(var(--color-border))]/30 text-left text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
                <tr>
                  <th className="px-4 py-3">Case No</th>
                  <th className="px-4 py-3">Customer</th>
                  <th className="px-4 py-3">Division</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Legal Amount</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-6 text-center text-[rgb(var(--color-muted))]">
                      Loading...
                    </td>
                  </tr>
                ) : page.items.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-10 text-center text-[rgb(var(--color-muted))]">
                      {activeFilterCount > 0
                        ? 'No cases match the active filters.'
                        : 'No cases yet. Click '}
                      {activeFilterCount === 0 && (
                        <strong>New Case</strong>
                      )}
                      {activeFilterCount === 0 && ' to file the first one.'}
                    </td>
                  </tr>
                ) : (
                  page.items.map((r) => {
                    const types = [r.is_criminal && 'Criminal', r.is_civil && 'Civil']
                      .filter(Boolean)
                      .join(' + ');
                    return (
                      <tr key={r.id} className="border-t border-[rgb(var(--color-border))]">
                        <td className="px-4 py-2 font-mono text-xs">{r.case_no}</td>
                        <td className="px-4 py-2">
                          {r.customer_name}
                          <div className="text-[10px] text-[rgb(var(--color-muted))]">
                            {r.customer_code}
                          </div>
                        </td>
                        <td className="px-4 py-2 text-xs">{r.division_name}</td>
                        <td className="px-4 py-2">{types || '-'}</td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          {Number(r.legal_filing_amount).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </td>
                        <td className="px-4 py-2">
                          <span
                            className={
                              'inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
                              (STATUS_COLOR[r.status] ??
                                'bg-slate-500/15 text-slate-600 border-slate-500/40')
                            }
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                          {r.current_stage}
                        </td>
                        <td className="px-4 py-2 text-xs text-[rgb(var(--color-muted))]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-2 text-right">
                          <Link
                            href={`/cases/${r.id}`}
                            className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                          >
                            <FileText className="h-3 w-3" /> Open
                          </Link>
                          <Link
                            href={`/cases/${r.id}/print`}
                            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
                          >
                            <Printer className="h-3 w-3" /> Print
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function FilterGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {title}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function CheckRow({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: () => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={onChange} className="h-3.5 w-3.5" />
      {label}
    </label>
  );
}

function toggle<T>(
  current: Set<T>,
  set: (next: Set<T>) => void,
  value: T,
): void {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  set(next);
}
