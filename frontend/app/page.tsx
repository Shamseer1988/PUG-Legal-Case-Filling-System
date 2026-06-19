'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuthStore } from '@/lib/auth';

export default function Home() {
  const router = useRouter();
  const { accessToken, hydrated } = useAuthStore();

  useEffect(() => {
    if (!hydrated) return;
    router.replace(accessToken ? '/dashboard' : '/login');
  }, [accessToken, hydrated, router]);

  return (
    <div className="grid min-h-screen place-items-center text-sm text-[rgb(var(--color-muted))]">
      Loading...
    </div>
  );
}
