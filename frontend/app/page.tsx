import { BrandHeader } from '@/components/BrandHeader';
import { API_URL } from '@/lib/utils';

async function fetchHealth(): Promise<{ status: string; version?: string } | null> {
  try {
    const r = await fetch(`${API_URL}/api/v1/health`, { cache: 'no-store' });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export default async function Home() {
  const health = await fetchHealth();

  const phases = [
    { n: 0, name: 'Foundation & Scaffolding', status: 'In progress' },
    { n: 1, name: 'Auth, RBAC, Masters', status: 'Pending' },
    { n: 2, name: 'Legal Case Entry Form', status: 'Pending' },
    { n: 3, name: 'Approval Workflow Engine', status: 'Pending' },
    { n: 4, name: 'Court Filing, Hearings, Expenses', status: 'Pending' },
    { n: 5, name: 'Notifications & Email Log', status: 'Pending' },
    { n: 6, name: 'Reports + Excel/PDF/Print Export', status: 'Pending' },
    { n: 7, name: 'Scheduled Reporting via Email', status: 'Pending' },
    { n: 8, name: 'Audit Log (Tamper-Evident)', status: 'Pending' },
    { n: 9, name: 'Backup & Restore (PugFin Parity)', status: 'Pending' },
    { n: 10, name: 'System Settings & Admin Console', status: 'Pending' },
    { n: 11, name: 'Executive Dashboard & Charts', status: 'Pending' },
    { n: 12, name: 'Hardening, Tests, Deploy', status: 'Pending' },
  ];

  return (
    <div>
      <BrandHeader />
      <main className="mx-auto max-w-6xl px-6 py-10">
        <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-6 shadow-soft">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">Welcome</h2>
              <p className="mt-1 text-sm text-[rgb(var(--color-muted))]">
                Local development scaffolding is live. Sign-in, masters and case
                entry arrive in Phase 1+.
              </p>
            </div>
            <div className="text-right">
              <div className="text-xs uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Backend
              </div>
              {health ? (
                <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  {health.status} · v{health.version}
                </span>
              ) : (
                <span className="inline-flex items-center gap-2 rounded-full border border-rose-500/40 bg-rose-500/10 px-3 py-1 text-xs font-semibold text-rose-700 dark:text-rose-300">
                  <span className="h-2 w-2 rounded-full bg-rose-500" />
                  Offline
                </span>
              )}
            </div>
          </div>
        </section>

        <section className="mt-8">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-pug-gold-600 dark:text-pug-gold-400">
            Delivery Phases
          </h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {phases.map((p) => (
              <div
                key={p.n}
                className="flex items-center gap-3 rounded-lg border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-pug-navy-700 text-sm font-bold text-pug-gold-300">
                  {p.n}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{p.name}</div>
                  <div className="text-xs text-[rgb(var(--color-muted))]">{p.status}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>
      <footer className="border-t border-[rgb(var(--color-border))] py-6 text-center text-xs text-[rgb(var(--color-muted))]">
        © Paris United Group Holding · Legal Case Control System
      </footer>
    </div>
  );
}
