'use client';

import { LogOut } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { ThemeToggle } from './ThemeToggle';
import { useAuthStore } from '@/lib/auth';

export function Topbar() {
  const router = useRouter();
  const me = useAuthStore((s) => s.me);
  const clear = useAuthStore((s) => s.clear);

  function logout() {
    clear();
    router.replace('/login');
  }

  return (
    <header className="flex h-16 items-center gap-3 border-b border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] px-6">
      <div className="text-sm font-semibold text-[rgb(var(--color-fg))]">
        Paris United Group Holding
      </div>
      <div className="ml-auto flex items-center gap-3">
        {me && (
          <div className="text-right text-xs">
            <div className="font-semibold">{me.full_name}</div>
            <div className="text-[rgb(var(--color-muted))]">
              {me.role}
              {me.is_super && (
                <span className="ml-1 rounded-full bg-pug-gold-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-300">
                  Super
                </span>
              )}
            </div>
          </div>
        )}
        <ThemeToggle />
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-2 rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-xs font-semibold hover:bg-[rgb(var(--color-border))]/40"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </header>
  );
}
