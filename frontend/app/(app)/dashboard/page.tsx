'use client';

import { useAuthStore } from '@/lib/auth';

export default function DashboardPage() {
  const me = useAuthStore((s) => s.me);

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-6 shadow-soft">
        <h1 className="text-xl font-semibold">Welcome, {me?.full_name?.split(' ')[0]}</h1>
        <p className="mt-1 text-sm text-[rgb(var(--color-muted))]">
          Phase 1 complete: auth, roles, users and masters are live. Real KPIs land in Phase 11
          once cases exist.
        </p>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          ['Open Cases', '—'],
          ['Pending Approvals', '—'],
          ['Next Hearing', '—'],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5"
          >
            <div className="text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
              {label}
            </div>
            <div className="mt-2 text-2xl font-bold">{value}</div>
          </div>
        ))}
      </section>
    </div>
  );
}
