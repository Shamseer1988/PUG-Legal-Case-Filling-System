'use client';

import { NotificationBell } from './NotificationBell';
import { ThemeToggle } from './ThemeToggle';

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] px-6">
      <div className="text-sm font-semibold text-[rgb(var(--color-fg))]">
        Paris United Group Holding
      </div>
      <div className="ml-auto flex items-center gap-3">
        <NotificationBell />
        <ThemeToggle />
      </div>
    </header>
  );
}
