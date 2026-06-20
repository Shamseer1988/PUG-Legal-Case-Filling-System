'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAuthStore, type Me } from '@/lib/auth';
import { useCapabilitiesStore } from '@/lib/capabilities';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { accessToken, me, setMe, clear, hydrated } = useAuthStore();
  const loadCaps = useCapabilitiesStore((s) => s.load);
  const caps = useCapabilitiesStore((s) => s.caps);
  const clearCaps = useCapabilitiesStore((s) => s.clear);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) {
      clearCaps();
      router.replace('/login');
      return;
    }
    if (me && caps) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        if (!me) {
          const fresh = await api<Me>('/api/v1/auth/me');
          setMe(fresh);
        }
        if (!caps) await loadCaps();
        setLoading(false);
      } catch (err) {
        if ((err as ApiError).status === 401) {
          clear();
          clearCaps();
          router.replace('/login');
        }
      }
    })();
  }, [hydrated, accessToken, me, caps, router, setMe, clear, loadCaps, clearCaps]);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-[rgb(var(--color-muted))]">
        Loading...
      </div>
    );
  }
  return <>{children}</>;
}
