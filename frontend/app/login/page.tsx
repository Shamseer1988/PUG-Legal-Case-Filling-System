'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api, ApiError, API_BASE } from '@/lib/api';
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
  const [logoErr, setLogoErr] = useState(false);

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
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-slate-950 p-6 overflow-hidden">
      {/* Glowing background shapes to create high premium look */}
      <div className="absolute top-1/4 left-1/4 h-96 w-96 rounded-full bg-pug-gold-500/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 h-96 w-96 rounded-full bg-pug-navy-500/20 blur-[120px] pointer-events-none" />

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <div className={`w-full max-w-md transform transition-all duration-700 ease-out ${error ? 'animate-shake' : ''}`}>
        {/* Centered Glassmorphic Card */}
        <div className="rounded-2xl border border-white/10 bg-white/5 p-8 backdrop-blur-md shadow-2xl transition hover:border-white/15">

          {/* Large Logo Header */}
          <div className="flex flex-col items-center text-center mb-8">
            <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-full border-2 border-pug-gold-500/20 bg-slate-900/50 shadow-lg mb-4 hover:scale-105 transition-transform duration-300">
              {logoErr ? (
                <div className="text-xl font-extrabold text-pug-gold-500">PUG</div>
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`${API_BASE}/api/v1/settings/public/logo`}
                  alt="Logo"
                  className="h-full w-full object-cover"
                  onError={() => setLogoErr(true)}
                />
              )}
            </div>
            <div>
              <h1 className="text-xs font-semibold uppercase tracking-[0.2em] text-pug-gold-400">
                Paris United Group Holding
              </h1>
              <h2 className="mt-1 text-xl font-bold tracking-tight text-white">
                Legal Case Control System
              </h2>
            </div>
          </div>

          <h3 className="text-lg font-semibold text-white">Sign in</h3>
          <p className="mt-1 text-xs text-slate-400">
            Enter your account credentials to access the workspace.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Email
              </label>
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder-slate-400 focus:border-pug-gold-500/80 focus:outline-none focus:ring-2 focus:ring-pug-gold-500/20 transition-all duration-200"
                placeholder="name@company.com"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                Password
              </label>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder-slate-400 focus:border-pug-gold-500/80 focus:outline-none focus:ring-2 focus:ring-pug-gold-500/20 transition-all duration-200"
                placeholder="••••••••"
              />
            </div>
            {needsTotp && (
              <div className="animate-fade-in">
                <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Authenticator Code
                </label>
                <input
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
                  className="w-full rounded-xl border border-pug-gold-500/60 bg-white/5 px-4 py-3 text-center font-mono text-lg tracking-[0.3em] text-white focus:border-pug-gold-500 focus:outline-none focus:ring-2 focus:ring-pug-gold-500/20"
                  placeholder="123456"
                />
              </div>
            )}
            {error && (
              <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2.5 text-xs text-rose-300">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-pug-gold-500 hover:bg-pug-gold-400 text-pug-navy-800 py-3 text-sm font-semibold transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-60 shadow-lg shadow-pug-gold-500/20 hover:shadow-pug-gold-500/30"
            >
              {busy ? 'Signing in...' : needsTotp ? 'Verify & Sign in' : 'Sign in'}
            </button>
          </form>

          <p className="mt-8 text-center text-[10px] text-slate-500">
            Default admin (seed): <code className="text-slate-400 bg-white/5 px-1 py-0.5 rounded">admin@pug.local</code> / <code className="text-slate-400 bg-white/5 px-1 py-0.5 rounded">Admin@123</code>
          </p>
        </div>
      </div>
    </div>
  );
}
