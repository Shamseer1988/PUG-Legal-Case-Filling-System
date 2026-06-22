'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import {
  LayoutDashboard,
  FileText,
  Briefcase,
  Building2,
  Landmark,
  Users,
  UserSquare2,
  Scale,
  Tag,
  ShieldCheck,
  Settings,
  Calendar,
  Banknote,
  Mail,
  ArrowRightLeft,
  BarChart3,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  LogOut,
  User,
  HardDrive,
  Activity,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/lib/auth';
import { API_BASE } from '@/lib/api';
import { MENU, useCapabilitiesStore } from '@/lib/capabilities';


type Item = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  menuId: string;
};

type Group = { title: string; items: Item[] };

const GROUPS: Group[] = [
  {
    title: 'Workspace',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, menuId: MENU.DASHBOARD },
      { href: '/profile', label: 'My Profile', icon: User, menuId: MENU.PROFILE },
    ],
  },
  {
    title: 'Transactions',
    items: [
      { href: '/cases', label: 'Cases', icon: FileText, menuId: MENU.CASES },
      { href: '/approvals', label: 'Approvals Inbox', icon: Briefcase, menuId: MENU.APPROVALS },
      { href: '/hearings', label: 'Hearings Calendar', icon: Calendar, menuId: MENU.HEARINGS },
      { href: '/cash-requests', label: 'Cash Requests', icon: Banknote, menuId: MENU.CASH_REQUESTS },
    ],
  },
  {
    title: 'Insights',
    items: [
      { href: '/reports', label: 'Reports', icon: BarChart3, menuId: MENU.REPORTS },
      { href: '/schedules', label: 'Scheduled Reports', icon: CalendarClock, menuId: MENU.SCHEDULED_REPORTS },
    ],
  },
  {
    title: 'Masters',
    items: [
      { href: '/masters/divisions', label: 'Divisions', icon: Building2, menuId: MENU.MASTERS_DIVISIONS },
      { href: '/masters/banks', label: 'Banks', icon: Landmark, menuId: MENU.MASTERS_BANKS },
      { href: '/masters/customers', label: 'Customers', icon: UserSquare2, menuId: MENU.MASTERS_CUSTOMERS },
      { href: '/masters/salesmen', label: 'Salesmen', icon: Users, menuId: MENU.MASTERS_SALESMEN },
      { href: '/masters/lawyers', label: 'Lawyers', icon: Scale, menuId: MENU.MASTERS_LAWYERS },
      { href: '/masters/case-types', label: 'Case Types', icon: Tag, menuId: MENU.MASTERS_CASE_TYPES },
    ],
  },
  {
    title: 'Admin',
    items: [
      { href: '/admin/users', label: 'Users', icon: Users, menuId: MENU.ADMIN_USERS },
      { href: '/admin/roles', label: 'Roles & Permissions', icon: ShieldCheck, menuId: MENU.ADMIN_ROLES },
      { href: '/admin/email-log', label: 'Email Log', icon: Mail, menuId: MENU.ADMIN_EMAIL_LOG },
      { href: '/admin/audit-log', label: 'Audit Log', icon: ShieldCheck, menuId: MENU.ADMIN_AUDIT_LOG },
      { href: '/admin/backups', label: 'Backup & Restore', icon: HardDrive, menuId: MENU.ADMIN_BACKUPS },
      { href: '/admin/settings', label: 'System Settings', icon: Settings, menuId: MENU.ADMIN_SETTINGS },
      { href: '/admin/diagnostics', label: 'Health & Diagnostics', icon: Activity, menuId: MENU.ADMIN_DIAGNOSTICS },
      { href: '/admin/bulk-reassign', label: 'Bulk Reassignment', icon: ArrowRightLeft, menuId: MENU.ADMIN_BULK_REASSIGN },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const me = useAuthStore((s) => s.me);
  const clear = useAuthStore((s) => s.clear);
  const caps = useCapabilitiesStore((s) => s.caps);
  const clearCaps = useCapabilitiesStore((s) => s.clear);

  const [logoErr, setLogoErr] = useState(false);

  // Sidebar collapsed state (icon-only)
  const [collapsed, setCollapsed] = useState(false);

  // Section expanded state — all sections start expanded
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(
    () => Object.fromEntries(GROUPS.map((g) => [g.title, true])),
  );

  function toggleSection(title: string) {
    setExpandedSections((prev) => ({ ...prev, [title]: !prev[title] }));
  }

  function logout() {
    clear();
    clearCaps();
    router.replace('/login');
  }

  return (
    <aside
      className={cn(
        'sticky top-0 hidden h-screen shrink-0 border-r border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] md:flex md:flex-col',
        'transition-all duration-300 ease-in-out',
        collapsed ? 'w-20' : 'w-64',
      )}
    >
      {/* Brand header with collapse/expand toggle */}
      <div
        className={cn(
          'flex h-16 items-center border-b border-[rgb(var(--color-border))] transition-all duration-300',
          collapsed ? 'pl-2.5 pr-1.5 gap-1 justify-between' : 'px-4 justify-between',
        )}
      >
        {logoErr ? (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pug-gold-500 text-xs font-extrabold text-pug-navy-800">
            PUG
          </div>
        ) : (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE}/api/v1/settings/public/logo`}
              alt="Logo"
              className="h-full w-full object-cover"
              onError={() => setLogoErr(true)}
            />
          </div>
        )}
        <div
          className={cn(
            'ml-3 overflow-hidden text-sm font-semibold leading-tight whitespace-nowrap transition-all duration-300',
            collapsed ? 'w-0 opacity-0 ml-0' : 'w-auto flex-1 opacity-100',
          )}
        >
          Legal Case
          <div className="text-[10px] uppercase tracking-widest text-pug-gold-600 dark:text-pug-gold-400">
            Control System
          </div>
        </div>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className={cn(
            'flex shrink-0 items-center justify-center rounded-md text-[rgb(var(--color-muted))] transition-all duration-300 hover:bg-[rgb(var(--color-border))]/50 hover:text-[rgb(var(--color-fg))]',
            collapsed ? 'h-6 w-6' : 'h-7 w-7',
          )}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden p-3">
        {GROUPS.map((g) => {
          // Until capabilities load, fall back to is_super so the admin
          // doesn't see an empty sidebar on first paint after refresh.
          const visible = g.items.filter((it) => {
            if (caps) return caps.menus.includes(it.menuId);
            return !!me?.is_super;
          });
          if (visible.length === 0) return null;

          const isExpanded = expandedSections[g.title] ?? true;

          return (
            <div key={g.title} className="mb-2">
              {/* Section header — clickable to expand/collapse */}
              <button
                type="button"
                onClick={() => !collapsed && toggleSection(g.title)}
                className={cn(
                  'group flex w-full items-center rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-[rgb(var(--color-muted))] transition-colors hover:text-[rgb(var(--color-fg))]',
                  collapsed && 'justify-center',
                )}
                title={collapsed ? g.title : undefined}
              >
                {!collapsed && (
                  <>
                    <ChevronDown
                      className={cn(
                        'mr-1.5 h-3 w-3 shrink-0 transition-transform duration-200',
                        !isExpanded && '-rotate-90',
                      )}
                    />
                    <span className="flex-1 text-left">{g.title}</span>
                  </>
                )}
                {collapsed && (
                  <div className="h-px w-6 bg-[rgb(var(--color-border))]" />
                )}
              </button>

              {/* Menu items with animated expand/collapse */}
              <div
                className={cn(
                  'overflow-hidden transition-all duration-200 ease-in-out',
                  !collapsed && !isExpanded ? 'max-h-0 opacity-0' : 'max-h-[500px] opacity-100',
                )}
              >
                <ul className={cn(collapsed ? 'mt-1 space-y-1' : 'mt-0.5')}>
                  {visible.map((it) => {
                    const Icon = it.icon;
                    const active = pathname === it.href || pathname.startsWith(it.href + '/');
                    return (
                      <li key={it.href}>
                        <Link
                          href={it.href}
                          title={collapsed ? it.label : undefined}
                          className={cn(
                            'group relative flex items-center rounded-md text-sm transition-colors duration-150',
                            collapsed
                              ? 'justify-center px-2 py-2'
                              : 'gap-2 px-2 py-2',
                            active
                              ? 'bg-pug-gold-500/15 font-semibold text-pug-gold-700 dark:text-pug-gold-300'
                              : 'text-[rgb(var(--color-fg))] hover:bg-[rgb(var(--color-border))]/40',
                          )}
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          <span
                            className={cn(
                              'overflow-hidden whitespace-nowrap transition-all duration-300',
                              collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100',
                            )}
                          >
                            {it.label}
                          </span>

                          {/* Tooltip on hover when collapsed */}
                          {collapsed && (
                            <span className="pointer-events-none absolute left-full z-50 ml-2 hidden whitespace-nowrap rounded-md bg-[rgb(var(--color-fg))] px-2.5 py-1.5 text-xs font-medium text-[rgb(var(--color-bg))] shadow-lg group-hover:block">
                              {it.label}
                            </span>
                          )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          );
        })}
      </nav>

      {/* Bottom section: User info + Notifications + Theme + Sign out */}
      <div className="border-t border-[rgb(var(--color-border))] p-3">
        {/* User info */}
        {me && (
          <div
            className={cn(
              'mb-2 flex items-center rounded-md px-2 py-2',
              collapsed ? 'justify-center' : 'gap-3',
            )}
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-pug-navy-500/15 text-pug-navy-600 dark:bg-pug-navy-400/20 dark:text-pug-navy-200">
              <User className="h-4 w-4" />
            </div>
            <div
              className={cn(
                'overflow-hidden whitespace-nowrap transition-all duration-300',
                collapsed ? 'w-0 opacity-0' : 'w-auto flex-1 opacity-100',
              )}
            >
              <div className="truncate text-xs font-semibold">{me.full_name}</div>
              <div className="flex items-center gap-1 text-[10px] text-[rgb(var(--color-muted))]">
                <span className="truncate">{me.role}</span>
                {me.is_super && (
                  <span className="shrink-0 rounded-full bg-pug-gold-500/20 px-1.5 py-0 text-[9px] font-bold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-300">
                    Super
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Sign out button */}
        <button
          type="button"
          onClick={logout}
          title="Sign out"
          className={cn(
            'group relative flex w-full items-center rounded-md text-[rgb(var(--color-muted))] transition-colors hover:bg-rose-500/10 hover:text-rose-600 dark:hover:text-rose-400',
            collapsed ? 'justify-center px-2 py-2' : 'gap-2 px-2 py-2',
          )}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          <span
            className={cn(
              'overflow-hidden whitespace-nowrap text-xs font-medium transition-all duration-300',
              collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100',
            )}
          >
            Sign out
          </span>

          {/* Tooltip when collapsed */}
          {collapsed && (
            <span className="pointer-events-none absolute left-full z-50 ml-2 hidden whitespace-nowrap rounded-md bg-[rgb(var(--color-fg))] px-2.5 py-1.5 text-xs font-medium text-[rgb(var(--color-bg))] shadow-lg group-hover:block">
              Sign out
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
