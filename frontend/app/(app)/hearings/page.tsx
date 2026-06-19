'use client';

import Link from 'next/link';
import { Calendar, MapPin } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type Item = {
  id: number;
  case_id: number;
  case_no: string;
  hearing_date: string;
  location: string;
  hearing_type: string;
  next_hearing_date: string | null;
};

export default function HearingsCalendarPage() {
  const [rows, setRows] = useState<Item[]>([]);
  const [days, setDays] = useState(60);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load(n: number) {
    setLoading(true);
    try {
      setRows(await api<Item[]>(`/api/v1/hearings/calendar?days=${n}`));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load(days);
  }, [days]);

  // Group by date
  const byDate = new Map<string, Item[]>();
  for (const r of rows) {
    const key = new Date(r.hearing_date).toISOString().slice(0, 10);
    const arr = byDate.get(key) ?? [];
    arr.push(r);
    byDate.set(key, arr);
  }
  const dates = [...byDate.keys()].sort();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Hearings Calendar</h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            Upcoming hearings and next-hearing dates across all cases.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          Range:
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-[rgb(var(--color-border))] bg-transparent px-2 py-1 text-sm"
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
          </select>
        </label>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-[rgb(var(--color-muted))]">Loading...</div>
      ) : dates.length === 0 ? (
        <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-10 text-center text-sm text-[rgb(var(--color-muted))] shadow-soft">
          No hearings scheduled in this window.
        </div>
      ) : (
        <div className="space-y-3">
          {dates.map((d) => (
            <div
              key={d}
              className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] shadow-soft"
            >
              <div className="flex items-center gap-2 border-b border-[rgb(var(--color-border))] bg-pug-gold-500/10 px-4 py-2 text-sm font-semibold text-pug-gold-700 dark:text-pug-gold-300">
                <Calendar className="h-4 w-4" />
                {new Date(d).toLocaleDateString(undefined, {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </div>
              <ul className="divide-y divide-[rgb(var(--color-border))]">
                {byDate.get(d)!.map((it) => (
                  <li key={`${it.id}-${it.hearing_date}`} className="flex items-center gap-3 px-4 py-3 text-sm">
                    <div className="w-20 shrink-0 text-xs font-mono text-[rgb(var(--color-muted))]">
                      {new Date(it.hearing_date).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <span className="font-semibold">{it.hearing_type}</span>
                        <Link
                          href={`/cases/${it.case_id}`}
                          className="text-xs font-mono text-pug-gold-700 hover:underline dark:text-pug-gold-400"
                        >
                          {it.case_no}
                        </Link>
                      </div>
                      {it.location && (
                        <div className="mt-0.5 flex items-center gap-1 text-xs text-[rgb(var(--color-muted))]">
                          <MapPin className="h-3 w-3" />
                          {it.location}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
