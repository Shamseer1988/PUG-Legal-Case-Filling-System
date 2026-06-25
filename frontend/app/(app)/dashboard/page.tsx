'use client';

import Link from 'next/link';
import {
  AlertTriangle,
  Banknote,
  Briefcase,
  CalendarClock,
  Check,
  ChevronRight,
  Clock,
  FileText,
  Gavel,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, ApiError } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';
import { useT, useLocale, tStatus } from '@/lib/i18n';

type Kpis = {
  total_cases: number;
  open_cases: number;
  approved_or_filed: number;
  rejected_cases: number;
  closed_cases: number;
  total_legal_amount: string;
  total_recovered: string;
  pending_my_inbox: number;
  overdue_count: number;
};

type StatusCount = { status: string; count: number };
type TrendPoint = { month: string; cases_created: number; cases_approved: number };
type DivisionRow = {
  division_id: number;
  division_name: string;
  total: number;
  by_status: Record<string, number>;
  total_legal_amount: string;
};
type Upcoming = {
  case_id: number;
  case_no: string;
  hearing_date: string;
  hearing_type: string;
  location: string;
  days_until: number;
};
type Alert = {
  severity: 'warn' | 'danger';
  title: string;
  detail: string;
  link: string | null;
  count: number;
};

const STATUS_COLOURS: Record<string, string> = {
  Draft: '#94a3b8',
  Submitted: '#c9a14a',
  'In Review': '#60a5fa',
  'Clarification Requested': '#f59e0b',
  Approved: '#10b981',
  Filed: '#22c55e',
  Rejected: '#ef4444',
  Closed: '#475569',
};

const ALL_STATUSES = [
  'Draft',
  'Submitted',
  'In Review',
  'Clarification Requested',
  'Approved',
  'Filed',
  'Rejected',
  'Closed',
];

export default function DashboardPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  const locale = useLocale();

  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [statusCounts, setStatusCounts] = useState<StatusCount[]>([]);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [divisions, setDivisions] = useState<DivisionRow[]>([]);
  const [upcoming, setUpcoming] = useState<Upcoming[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const [k, s, t, d, u, a] = await Promise.all([
        api<Kpis>('/api/v1/dashboard/kpis'),
        api<StatusCount[]>('/api/v1/dashboard/status-breakdown'),
        api<TrendPoint[]>('/api/v1/dashboard/trend'),
        api<DivisionRow[]>('/api/v1/dashboard/division-heatmap'),
        api<Upcoming[]>('/api/v1/dashboard/upcoming-hearings?days=30&limit=8'),
        api<Alert[]>('/api/v1/dashboard/alerts'),
      ]);
      setKpis(k);
      setStatusCounts(s);
      setTrend(t);
      setDivisions(d);
      setUpcoming(u);
      setAlerts(a);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            {t('dashboard.welcome')}
            {me?.full_name ? `, ${me.full_name.split(' ')[0]}` : ''}
          </h1>
          <p className="text-xs text-[rgb(var(--color-muted))]">
            {t('dashboard.live_overview')}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40 disabled:opacity-50"
        >
          <RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')} /> {t('btn.refresh')}
        </button>
      </div>

      {err && (
        <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
          {err}
        </div>
      )}

      {/* Alerts panel */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((a, i) => (
            <Link
              key={i}
              href={a.link ?? '#'}
              className={
                'flex items-start gap-3 rounded-xl border px-4 py-3 text-sm shadow-soft transition hover:translate-x-0.5 ' +
                (a.severity === 'danger'
                  ? 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300'
                  : 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300')
              }
            >
              {a.severity === 'danger' ? (
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <div className="font-semibold">{a.title}</div>
                <div className="text-xs opacity-90">{a.detail}</div>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0" />
            </Link>
          ))}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label={t('dashboard.kpi.total_cases')}
          value={kpis?.total_cases ?? 0}
          icon={<FileText className="h-4 w-4" />}
          accent="navy"
          href="/cases"
        />
        <KpiCard
          label={t('dashboard.kpi.open')}
          value={kpis?.open_cases ?? 0}
          icon={<Briefcase className="h-4 w-4" />}
          accent="gold"
          href="/cases"
        />
        <KpiCard
          label={t('dashboard.kpi.approved_filed')}
          value={kpis?.approved_or_filed ?? 0}
          icon={<Gavel className="h-4 w-4" />}
          accent="green"
          href="/cases"
        />
        <KpiCard
          label={t('dashboard.kpi.legal_amount')}
          value={formatCurrency(kpis?.total_legal_amount ?? '0')}
          icon={<TrendingUp className="h-4 w-4" />}
          accent="navy"
        />
        <KpiCard
          label={t('dashboard.kpi.cash_paid')}
          value={formatCurrency(kpis?.total_recovered ?? '0')}
          icon={<Banknote className="h-4 w-4" />}
          accent="green"
          href="/cash-requests"
        />
        <KpiCard
          label={t('dashboard.kpi.my_inbox')}
          value={kpis?.pending_my_inbox ?? 0}
          icon={<Check className="h-4 w-4" />}
          accent={kpis && kpis.overdue_count > 0 ? 'red' : 'gold'}
          sub={kpis && kpis.overdue_count > 0 ? `${kpis.overdue_count} ${t('dashboard.kpi.overdue')}` : undefined}
          href="/approvals"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title={t('dashboard.panel.monthly_activity')} className="lg:col-span-2">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <CartesianGrid stroke="rgb(var(--color-border))" strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="rgb(var(--color-muted))" />
                <YAxis tick={{ fontSize: 11 }} stroke="rgb(var(--color-muted))" allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: 'rgb(var(--color-card))',
                    border: '1px solid rgb(var(--color-border))',
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="cases_created"
                  name={t('dashboard.legend.created')}
                  stroke="#1a234a"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
                <Line
                  type="monotone"
                  dataKey="cases_approved"
                  name={t('dashboard.legend.approved')}
                  stroke="#c9a14a"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title={t('dashboard.panel.status_breakdown')}>
          {statusCounts.length === 0 ? (
            <EmptyState text={t('dashboard.empty.no_cases')} />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={statusCounts.map((s) => ({
                      ...s,
                      status: tStatus(locale, s.status),
                    }))}
                    dataKey="count"
                    nameKey="status"
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                  >
                    {statusCounts.map((s, i) => (
                      <Cell
                        key={i}
                        fill={STATUS_COLOURS[s.status] ?? '#94a3b8'}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'rgb(var(--color-card))',
                      border: '1px solid rgb(var(--color-border))',
                      fontSize: 12,
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 10 }}
                    iconSize={8}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>
      </div>

      {/* Heatmap + Upcoming Hearings */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title={t('dashboard.panel.division_status')} className="lg:col-span-2">
          {divisions.length === 0 ? (
            <EmptyState text={t('dashboard.empty.no_cases')} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="px-2 py-2 text-left text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                      {t('dashboard.col.division')}
                    </th>
                    {ALL_STATUSES.map((s) => (
                      <th
                        key={s}
                        className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]"
                      >
                        {tStatus(locale, s)}
                      </th>
                    ))}
                    <th className="px-2 py-2 text-right text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
                      {t('dashboard.col.total')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {divisions.map((d) => {
                    const max = Math.max(
                      ...ALL_STATUSES.map((s) => d.by_status[s] ?? 0),
                      1,
                    );
                    return (
                      <tr key={d.division_id} className="border-t border-[rgb(var(--color-border))]">
                        <td className="px-2 py-2 font-semibold">{d.division_name}</td>
                        {ALL_STATUSES.map((s) => {
                          const n = d.by_status[s] ?? 0;
                          const intensity = max > 0 ? n / max : 0;
                          const colour = STATUS_COLOURS[s] ?? '#94a3b8';
                          return (
                            <td
                              key={s}
                              className="px-2 py-2 text-right tabular-nums"
                              style={{
                                background: n > 0 ? `${colour}${alpha(intensity)}` : 'transparent',
                                color: n > 0 ? '#0b1020' : 'rgb(var(--color-muted))',
                                fontWeight: n > 0 ? 600 : 400,
                              }}
                            >
                              {n || '-'}
                            </td>
                          );
                        })}
                        <td className="px-2 py-2 text-right font-bold">{d.total}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title={t('dashboard.panel.upcoming_hearings')}>
          {upcoming.length === 0 ? (
            <EmptyState text={t('dashboard.empty.no_hearings')} />
          ) : (
            <ul className="space-y-2">
              {upcoming.map((h, i) => (
                <li key={`${h.case_id}-${i}`}>
                  <Link
                    href={`/cases/${h.case_id}`}
                    className="flex items-start gap-3 rounded-md border border-[rgb(var(--color-border))] p-2 text-sm transition hover:bg-[rgb(var(--color-border))]/30"
                  >
                    <div className="flex h-9 w-12 flex-col items-center justify-center rounded-md bg-pug-gold-500/20 text-center text-pug-gold-700 dark:text-pug-gold-300">
                      <div className="text-[9px] uppercase leading-none">
                        {t('dashboard.in_days').replace('{n}', String(h.days_until))}
                      </div>
                      <CalendarClock className="h-3 w-3" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold">{h.hearing_type}</div>
                      <div className="text-[10px] text-[rgb(var(--color-muted))]">
                        {new Date(h.hearing_date).toLocaleString()}
                        {h.location && ` · ${h.location}`}
                      </div>
                      <div className="font-mono text-[10px] text-pug-gold-700 dark:text-pug-gold-400">
                        {h.case_no}
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {/* Status bar chart */}
      <Panel title={t('dashboard.panel.status_count')}>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={statusCounts.map((s) => ({ ...s, status: tStatus(locale, s.status) }))}>
              <CartesianGrid stroke="rgb(var(--color-border))" strokeDasharray="3 3" />
              <XAxis dataKey="status" tick={{ fontSize: 10 }} stroke="rgb(var(--color-muted))" />
              <YAxis tick={{ fontSize: 11 }} stroke="rgb(var(--color-muted))" allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: 'rgb(var(--color-card))',
                  border: '1px solid rgb(var(--color-border))',
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {statusCounts.map((s, i) => (
                  <Cell key={i} fill={STATUS_COLOURS[s.status] ?? '#94a3b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
    </div>
  );
}

function KpiCard({
  label,
  value,
  icon,
  accent,
  sub,
  href,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  accent: 'navy' | 'gold' | 'green' | 'red';
  sub?: string;
  href?: string;
}) {
  const accentCls = {
    navy: 'bg-pug-navy-700 text-pug-gold-300',
    gold: 'bg-pug-gold-500 text-pug-navy-800',
    green: 'bg-emerald-500 text-white',
    red: 'bg-rose-500 text-white',
  }[accent];

  const inner = (
    <div className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft transition hover:border-pug-gold-500/60">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
          {label}
        </div>
        <div className={`flex h-7 w-7 items-center justify-center rounded-md ${accentCls}`}>
          {icon}
        </div>
      </div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {sub && <div className="text-[10px] text-rose-600">{sub}</div>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function Panel({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={
        'rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-4 shadow-soft ' +
        (className ?? '')
      }
    >
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
        {title}
      </h3>
      {children}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="grid h-32 place-items-center text-xs text-[rgb(var(--color-muted))]">
      {text}
    </div>
  );
}

function alpha(intensity: number): string {
  const a = Math.round(0.25 + intensity * 0.7 * 255)
    .toString(16)
    .padStart(2, '0');
  return a;
}

function formatCurrency(s: string): string {
  const n = Number(s);
  if (!isFinite(n) || Number.isNaN(n)) return '0.00';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
