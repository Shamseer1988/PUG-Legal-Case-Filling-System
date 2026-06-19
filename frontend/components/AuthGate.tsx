'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAuthStore, type Me } from '@/lib/auth';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { accessToken, me, setMe, clear, hydrated } = useAuthStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hydrated) return;
    if (!accessToken) {
      router.replace('/login');
      return;
    }
    if (me) {
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const fresh = await api<Me>('/api/v1/auth/me');
        setMe(fresh);
        setLoading(false);
      } catch (err) {
        if ((err as ApiError).status === 401) {
          clear();
          router.replace('/login');
        }
      }
    })();
  }, [hydrated, accessToken, me, router, setMe, clear]);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-sm text-[rgb(var(--color-muted))]">
        Loading...
      </div>
    );
  }
  return <>{children}</>;
}
