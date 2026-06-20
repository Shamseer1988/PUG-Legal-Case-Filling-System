'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import { menuFromPath, useCapabilitiesStore } from '@/lib/capabilities';

/** Wraps the (app) layout so a user typing an out-of-scope URL
 *  directly into the address bar gets a friendly Forbidden screen
 *  instead of either a half-rendered page or a wall of 403 toasts
 *  from per-component API calls. */
export function RouteGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const caps = useCapabilitiesStore((s) => s.caps);

  // Until capabilities load, render children — AuthGate already
  // shows a loading spinner during the initial fetch, so by the
  // time anything paints here caps should be present.
  if (!caps) return <>{children}</>;

  const required = menuFromPath(pathname);
  // Unmapped paths (e.g. nested utility pages) are allowed.
  if (!required) return <>{children}</>;
  if (caps.menus.includes(required)) return <>{children}</>;

  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400">
        <ShieldAlert className="h-7 w-7" />
      </div>
      <h1 className="text-lg font-semibold">You don&apos;t have access to this page</h1>
      <p className="mt-2 text-sm text-[rgb(var(--color-muted))]">
        Your role ({caps.role || 'Unknown'}) doesn&apos;t include access to{' '}
        <code className="rounded bg-[rgb(var(--color-border))]/40 px-1.5 py-0.5 text-xs">
          {pathname}
        </code>
        . Contact an administrator if you believe this is a mistake.
      </p>
      <Link
        href="/dashboard"
        className="mt-6 inline-flex items-center rounded-md bg-pug-gold-500 px-4 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400"
      >
        Go to Dashboard
      </Link>
    </div>
  );
}
