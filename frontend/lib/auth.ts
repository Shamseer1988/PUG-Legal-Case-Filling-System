'use client';

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type Me = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  permissions: string[];
  is_super: boolean;
  divisions: number[];
};

type State = {
  accessToken: string | null;
  refreshToken: string | null;
  me: Me | null;
  hydrated: boolean;
  setTokens: (access: string, refresh: string) => void;
  setMe: (me: Me | null) => void;
  clear: () => void;
};

export const useAuthStore = create<State>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      me: null,
      hydrated: false,
      setTokens: (access, refresh) => set({ accessToken: access, refreshToken: refresh }),
      setMe: (me) => set({ me }),
      clear: () => set({ accessToken: null, refreshToken: null, me: null }),
    }),
    {
      name: 'pug-legal-auth',
      storage: createJSONStorage(() => localStorage),
      onRehydrateStorage: () => (state) => {
        if (state) state.hydrated = true;
      },
    },
  ),
);

export function hasPermission(me: Me | null, perm: string): boolean {
  if (!me) return false;
  if (me.is_super) return true;
  if (me.permissions.includes('*')) return true;
  if (me.permissions.includes(perm)) return true;
  for (const p of me.permissions) {
    if (p.endsWith(':*') && perm.startsWith(p.slice(0, -1))) return true;
  }
  return false;
}
