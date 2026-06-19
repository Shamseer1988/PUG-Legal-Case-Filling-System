'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
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

  return (
    <aside className="hidden w-64 shrink-0 border-r border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] md:block">
      <div className="flex h-16 items-center gap-3 border-b border-[rgb(var(--color-border))] px-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-pug-gold-500 text-xs font-extrabold text-pug-navy-800">
          PUG
        </div>
        <div className="text-sm font-semibold leading-tight">
          Legal Case
          <div className="text-[10px] uppercase tracking-widest text-pug-gold-600 dark:text-pug-gold-400">
            Control System
          </div>
        </div>
      </div>
      <nav className="p-3">
        {GROUPS.map((g) => {
          const visible = g.items.filter((it) => {
            if (it.super) return !!me?.is_super;
            if (it.perm) return hasPermission(me, it.perm);
            return true;
          });
          if (visible.length === 0) return null;
          return (
            <div key={g.title} className="mb-4">
              <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-[rgb(var(--color-muted))]">
                {g.title}
              </div>
              <ul>
                {visible.map((it) => {
                  const Icon = it.icon;
                  const active = pathname === it.href || pathname.startsWith(it.href + '/');
                  return (
                    <li key={it.href}>
                      <Link
                        href={it.href}
                        className={cn(
                          'flex items-center gap-2 rounded-md px-2 py-2 text-sm transition',
                          active
                            ? 'bg-pug-gold-500/15 font-semibold text-pug-gold-700 dark:text-pug-gold-300'
                            : 'text-[rgb(var(--color-fg))] hover:bg-[rgb(var(--color-border))]/40',
                        )}
                      >
                        <Icon className="h-4 w-4" />
                        {it.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
