'use client';

import { CheckCircle2, ShieldCheck, ShieldOff } from 'lucide-react';
import { useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAuthStore, type Me } from '@/lib/auth';

type EnrollResponse = {
  secret: string;
  otpauth_url: string;
  qr_data_url: string;
};

export default function ProfilePage() {
  const me = useAuthStore((s) => s.me);
  const setMe = useAuthStore((s) => s.setMe);
  const [enroll, setEnroll] = useState<EnrollResponse | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function refreshMe() {
    try {
      const fresh = await api<Me>('/api/v1/auth/me');
      setMe(fresh);
    } catch {
      /* ignore */
    }
  }

  async function startEnroll() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      setEnroll(await api<EnrollResponse>('/api/v1/auth/2fa/enroll', { method: 'POST' }));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setErr(null);
    try {
      await api('/api/v1/auth/2fa/verify', { method: 'POST', body: { code } });
      setInfo('Two-factor authentication enabled.');
      setEnroll(null);
      setCode('');
      refreshMe();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    if (!confirm('Disable two-factor authentication?')) return;
    setBusy(true);
    setErr(null);
    try {
      await api('/api/v1/auth/2fa/disable', { method: 'POST' });
      setInfo('Two-factor authentication disabled.');
      refreshMe();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold">My Profile</h1>
        <p className="text-xs text-[rgb(var(--color-muted))]">
          Account details and security.
        </p>
      </div>

      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          Identity
        </h2>
        <dl className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
          <Pair k="Name" v={me?.full_name ?? '-'} />
          <Pair k="Email" v={me?.email ?? '-'} />
          <Pair k="Role" v={me?.role ?? '-'} />
          <Pair k="Super User" v={me?.is_super ? 'Yes' : 'No'} />
        </dl>
      </section>

      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
            Two-Factor Authentication
          </h2>
          {me?.totp_enabled ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300">
              <ShieldCheck className="h-3 w-3" /> Enabled
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-rose-700 dark:text-rose-300">
              <ShieldOff className="h-3 w-3" /> Disabled
            </span>
          )}
        </div>

        {err && (
          <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
            {err}
          </div>
        )}
        {info && (
          <div className="mb-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
            {info}
          </div>
        )}

        {me?.totp_enabled ? (
          <div>
            <p className="mb-3 text-sm text-[rgb(var(--color-muted))]">
              An authenticator app is required on every sign-in.
            </p>
            <button
              onClick={disable}
              disabled={busy}
              className="rounded-md border border-rose-500/40 px-3 py-2 text-sm text-rose-600 hover:bg-rose-500/10 disabled:opacity-50"
            >
              Disable 2FA
            </button>
          </div>
        ) : !enroll ? (
          <div>
            <p className="mb-3 text-sm text-[rgb(var(--color-muted))]">
              Add a one-time-password layer (Google Authenticator, 1Password, Authy).
            </p>
            <button
              onClick={startEnroll}
              disabled={busy}
              className="rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
            >
              Set up 2FA
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-[auto_1fr]">
              <img
                src={enroll.qr_data_url}
                alt="2FA QR code"
                className="h-40 w-40 rounded-md border border-[rgb(var(--color-border))] bg-white p-2"
              />
              <div className="text-sm">
                <div className="mb-2 font-semibold">Scan or paste this secret:</div>
                <code className="block break-all rounded-md bg-[rgb(var(--color-border))]/30 px-2 py-1 font-mono text-xs">
                  {enroll.secret}
                </code>
                <div className="mt-3 text-xs text-[rgb(var(--color-muted))]">
                  Use any TOTP app, then enter the 6-digit code below to activate.
                </div>
              </div>
            </div>
            <div className="flex items-end gap-2">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
                  6-digit code
                </span>
                <input
                  inputMode="numeric"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="123456"
                  className="w-40 rounded-md border border-pug-gold-500/60 bg-transparent px-3 py-2 text-center font-mono text-lg tracking-widest focus:border-pug-gold-500 focus:outline-none"
                />
              </label>
              <button
                onClick={verify}
                disabled={busy || code.length !== 6}
                className="rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
              >
                Activate
              </button>
              <button
                onClick={() => {
                  setEnroll(null);
                  setCode('');
                }}
                className="rounded-md border border-[rgb(var(--color-border))] px-3 py-2 text-sm hover:bg-[rgb(var(--color-border))]/40"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function Pair({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {k}
      </div>
      <div className="text-sm">{v}</div>
    </div>
  );
}
