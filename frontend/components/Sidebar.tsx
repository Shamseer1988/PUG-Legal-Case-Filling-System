'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
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
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { hasPermission, useAuthStore } from '@/lib/auth';

type Item = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  perm?: string;
  super?: boolean;
};

type Group = { title: string; items: Item[] };

const GROUPS: Group[] = [
  {
    title: 'Workspace',
    items: [{ href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    title: 'Transactions',
    items: [
      { href: '/cases', label: 'Cases', icon: FileText, perm: 'cases:read' },
      { href: '/approvals', label: 'Approvals Inbox', icon: Briefcase, perm: 'cases:read' },
      { href: '/hearings', label: 'Hearings Calendar', icon: Calendar, perm: 'cases:read' },
      {
        href: '/cash-requests',
        label: 'Cash Requests',
        icon: Banknote,
        perm: 'cases:read',
      },
    ],
  },
  {
    title: 'Insights',
    items: [{ href: '/reports', label: 'Reports', icon: BarChart3, perm: 'cases:read' }],
  },
  {
    title: 'Masters',
    items: [
      { href: '/masters/divisions', label: 'Divisions', icon: Building2, perm: 'masters:read' },
      { href: '/masters/banks', label: 'Banks', icon: Landmark, perm: 'masters:read' },
      { href: '/masters/customers', label: 'Customers', icon: UserSquare2, perm: 'masters:read' },
      { href: '/masters/salesmen', label: 'Salesmen', icon: Users, perm: 'masters:read' },
      { href: '/masters/lawyers', label: 'Lawyers', icon: Scale, perm: 'masters:read' },
      { href: '/masters/case-types', label: 'Case Types', icon: Tag, perm: 'masters:read' },
    ],
  },
  {
    title: 'Admin',
    items: [
      { href: '/admin/users', label: 'Users', icon: Users, perm: 'users:read' },
      { href: '/admin/roles', label: 'Roles & Permissions', icon: ShieldCheck, perm: 'roles:read' },
      { href: '/admin/email-log', label: 'Email Log', icon: Mail, perm: 'admin:email_log' },
      { href: '/admin/settings', label: 'System Settings (Phase 10)', icon: Settings, super: true },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const me = useAuthStore((s) => s.me);

  // Sidebar collapsed state (icon-only)
  const [collapsed, setCollapsed] = useState(false);

  // Section expanded state — all sections start expanded
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(
    () => Object.fromEntries(GROUPS.map((g) => [g.title, true])),
  );

  function toggleSection(title: string) {
    setExpandedSections((prev) => ({ ...prev, [title]: !prev[title] }));
  }

  return (
    <aside
      className={cn(
        'relative hidden shrink-0 border-r border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] md:flex md:flex-col',
        'transition-all duration-300 ease-in-out',
        collapsed ? 'w-[68px]' : 'w-64',
      )}
    >
      {/* Brand header */}
      <div className="flex h-16 items-center gap-3 border-b border-[rgb(var(--color-border))] px-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pug-gold-500 text-xs font-extrabold text-pug-navy-800">
          PUG
        </div>
        <div
          className={cn(
            'overflow-hidden text-sm font-semibold leading-tight whitespace-nowrap transition-all duration-300',
            collapsed ? 'w-0 opacity-0' : 'w-auto opacity-100',
          )}
        >
          Legal Case
          <div className="text-[10px] uppercase tracking-widest text-pug-gold-600 dark:text-pug-gold-400">
            Control System
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden p-3">
        {GROUPS.map((g) => {
          const visible = g.items.filter((it) => {
            if (it.super) return !!me?.is_super;
            if (it.perm) return hasPermission(me, it.perm);
            return true;
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

      {/* Collapse / Expand toggle button at the bottom */}
      <div className="border-t border-[rgb(var(--color-border))] p-3">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className={cn(
            'flex w-full items-center rounded-md px-2 py-2 text-sm text-[rgb(var(--color-muted))] transition-colors hover:bg-[rgb(var(--color-border))]/40 hover:text-[rgb(var(--color-fg))]',
            collapsed ? 'justify-center' : 'gap-2',
          )}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4 shrink-0" />
          ) : (
            <>
              <ChevronLeft className="h-4 w-4 shrink-0" />
              <span className="overflow-hidden whitespace-nowrap text-xs font-medium">
                Collapse
              </span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
