'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { API_BASE } from '@/lib/api';
import { useAuthStore } from '@/lib/auth';

export default function CasePrintPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const token = useAuthStore((s) => s.accessToken);
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    if (!token) {
      setErr('Not signed in.');
      return;
    }
    (async () => {
      const r = await fetch(`${API_BASE}/api/v1/cases/${id}/print`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!r.ok) {
        setErr(`Failed (${r.status})`);
        return;
      }
      setHtml(await r.text());
      setTimeout(() => window.print(), 400);
    })();
  }, [id, token]);

  if (err) return <div className="p-6 text-sm text-rose-600">{err}</div>;
  if (!html) return <div className="p-6 text-sm">Preparing print view...</div>;
  return (
    <iframe
      title="Case print"
      style={{ width: '100%', height: 'calc(100vh - 80px)', border: 'none' }}
      srcDoc={html}
    />
  );
}
