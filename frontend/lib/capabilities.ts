'use client';

import { create } from 'zustand';
import { api } from './api';

export type DataScope = 'all' | 'own_divisions';

export type Capabilities = {
  role: string;
  is_super: boolean;
  menus: string[];
  actions: string[];
  scope: DataScope;
  divisions: number[];
};

type State = {
  caps: Capabilities | null;
  loading: boolean;
  load: () => Promise<void>;
  clear: () => void;
};

export const useCapabilitiesStore = create<State>((set, get) => ({
  caps: null,
  loading: false,
  load: async () => {
    if (get().loading) return;
    set({ loading: true });
    try {
      const caps = await api<Capabilities>('/api/v1/auth/me/capabilities');
      set({ caps, loading: false });
    } catch {
      set({ caps: null, loading: false });
    }
  },
  clear: () => set({ caps: null }),
}));

export function canSeeMenu(caps: Capabilities | null, menuId: string): boolean {
  if (!caps) return false;
  return caps.menus.includes(menuId);
}

export function canDoAction(caps: Capabilities | null, actionId: string): boolean {
  if (!caps) return false;
  return caps.actions.includes(actionId);
}

// Canonical menu IDs — must match backend/app/core/permissions.py
export const MENU = {
  DASHBOARD: 'dashboard',
  PROFILE: 'profile',
  CASES: 'cases',
  APPROVALS: 'approvals',
  HEARINGS: 'hearings',
  CASH_REQUESTS: 'cash_requests',
  REPORTS: 'reports',
  SCHEDULED_REPORTS: 'scheduled_reports',
  MASTERS_DIVISIONS: 'masters.divisions',
  MASTERS_BANKS: 'masters.banks',
  MASTERS_CUSTOMERS: 'masters.customers',
  MASTERS_SALESMEN: 'masters.salesmen',
  MASTERS_LAWYERS: 'masters.lawyers',
  MASTERS_CASE_TYPES: 'masters.case_types',
  ADMIN_USERS: 'admin.users',
  ADMIN_ROLES: 'admin.roles',
  ADMIN_EMAIL_LOG: 'admin.email_log',
  ADMIN_AUDIT_LOG: 'admin.audit_log',
  ADMIN_BACKUPS: 'admin.backups',
  ADMIN_SETTINGS: 'admin.settings',
  ADMIN_DIAGNOSTICS: 'admin.diagnostics',
} as const;

// Canonical action IDs — must match backend/app/core/permissions.py
export const ACTION = {
  CASE_CREATE: 'case.create',
  CASE_APPROVE_SALES_MGR: 'case.approve.sales_mgr',
  CASE_APPROVE_DIV_MGR: 'case.approve.div_mgr',
  CASE_APPROVE_AUDIT: 'case.approve.audit',
  CASE_APPROVE_FM: 'case.approve.fm',
  CASE_APPROVE_ED: 'case.approve.ed',
  CASE_APPROVE_FINAL: 'case.approve.final',
  CASE_LAWYER_APPROVE: 'case.lawyer.approve',
  CASE_FILE: 'case.file',
  CASE_CLOSE: 'case.close',
  CASH_REQUEST: 'cash.request',
  CASH_APPROVE: 'cash.approve',
  CASH_PAY: 'cash.pay',
} as const;
