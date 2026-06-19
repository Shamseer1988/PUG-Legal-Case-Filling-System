'use client';

import Link from 'next/link';
import { BarChart3, ChevronRight } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';

type ReportDescriptor = {
  key: string;
  name: string;
  description: string;
};

export default function ReportsIndexPage() {
  const [items, setItems] = useState<ReportDescriptor[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<ReportDescriptor[]>('/api/v1/reports')
      .then(setItems)
      .catch((e) => setErr((e as ApiError).message));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Reports</h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Run any report with parameters, preview the table, then download Excel or PDF.
        </p>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {items.map((r) => (
          <Link
            key={r.key}
            href={`/reports/${r.key}`}
            className="group flex items-start gap-3 rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft transition hover:border-pug-gold-500"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-pug-navy-700 text-pug-gold-300">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-semibold">
                {r.name}
                <ChevronRight className="h-4 w-4 text-[rgb(var(--color-muted))] transition group-hover:translate-x-0.5 group-hover:text-pug-gold-700" />
              </div>
              <div className="text-xs text-[rgb(var(--color-muted))]">{r.description}</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
