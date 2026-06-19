'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAuthStore, type Me } from '@/lib/auth';
import { ThemeToggle } from '@/components/ThemeToggle';

export default function LoginPage() {
  const router = useRouter();
  const { accessToken, setTokens, setMe } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [needsTotp, setNeedsTotp] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (accessToken) router.replace('/dashboard');
  }, [accessToken, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { email, password };
      if (needsTotp) body.totp_code = totpCode;
      const tokens = await api<{ access_token: string; refresh_token: string }>(
        '/api/v1/auth/login',
        { method: 'POST', body, auth: false },
      );
      setTokens(tokens.access_token, tokens.refresh_token);
      const me = await api<Me>('/api/v1/auth/me');
      setMe(me);
      router.replace('/dashboard');
    } catch (err) {
      const e = err as ApiError;
      // Surface the 2FA challenge cleanly
      if (e.message === 'totp_required' || e.message === 'totp_invalid') {
        setNeedsTotp(true);
        setError(
          e.message === 'totp_invalid'
            ? 'Invalid 6-digit code. Try again.'
            : 'Enter the 6-digit code from your authenticator app.',
        );
      } else {
        setError(e.message || 'Login failed');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen grid-cols-1 md:grid-cols-2">
      {/* Brand side */}
      <div className="relative hidden flex-col justify-between bg-gradient-to-br from-pug-navy-800 via-pug-navy-600 to-pug-navy-500 p-10 text-white md:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-pug-gold-500 font-extrabold text-pug-navy-800 shadow-gold">
            PUG
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-widest text-pug-gold-300">
              Paris United Group Holding
            </div>
            <div className="text-base font-semibold">Legal Case Control System</div>
          </div>
        </div>
        <div>
          <h2 className="text-3xl font-bold leading-tight">Centralised legal case management.</h2>
          <p className="mt-3 max-w-md text-sm text-pug-navy-100">
            From intake to court filing to closure — branded workflows, audit trails and
            executive dashboards in one place.
          </p>
        </div>
        <div className="text-xs text-pug-navy-100">
          &copy; Paris United Group Holding
        </div>
      </div>

      {/* Form side */}
      <div className="flex flex-col items-center justify-center p-6">
        <div className="absolute right-4 top-4">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-sm rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-8 shadow-soft">
          <div className="mb-6 flex items-center gap-2 md:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pug-gold-500 font-extrabold text-pug-navy-800">
              PUG
            </div>
            <div className="text-sm font-semibold">Legal Case Control System</div>
          </div>
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="mt-1 text-sm text-[rgb(var(--color-muted))]">
            Use your PUG account credentials.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Email
              </label>
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                Password
              </label>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
              />
            </div>
            {needsTotp && (
              <div>
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                  Authenticator Code
                </label>
                <input
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  className="w-full rounded-md border border-pug-gold-500/60 bg-transparent px-3 py-2 text-center font-mono text-lg tracking-widest focus:border-pug-gold-500 focus:outline-none"
                  placeholder="123456"
                />
              </div>
            )}
            {error && (
              <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-pug-gold-500 px-4 py-2 text-sm font-semibold text-pug-navy-800 transition hover:bg-pug-gold-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? 'Signing in...' : needsTotp ? 'Verify & Sign in' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-xs text-[rgb(var(--color-muted))]">
            Default admin (seed): <code>admin@pug.local</code> / <code>Admin@123</code>
          </p>
        </div>
      </div>
    </div>
  );
}
