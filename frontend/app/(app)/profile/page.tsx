'use client';

import { CheckCircle2, KeyRound, PenLine, ShieldCheck, ShieldOff, Trash2, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api, ApiError, API_BASE } from '@/lib/api';
import { useAuthStore, type Me } from '@/lib/auth';

type EnrollResponse = {
  secret: string;
  otpauth_url: string;
  qr_data_url: string;
};

export default function ProfilePage() {
  const me = useAuthStore((s) => s.me);
  const setMe = useAuthStore((s) => s.setMe);
  const token = useAuthStore((s) => s.accessToken);
  const [enroll, setEnroll] = useState<EnrollResponse | null>(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // ---- Change password ----
  const [pwForm, setPwForm] = useState({ current: '', next: '', confirm: '' });
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [pwInfo, setPwInfo] = useState<string | null>(null);
  const [pwBusy, setPwBusy] = useState(false);

  // ---- Signature ----
  const sigInputRef = useRef<HTMLInputElement | null>(null);
  const [sigErr, setSigErr] = useState<string | null>(null);
  const [sigInfo, setSigInfo] = useState<string | null>(null);
  const [sigBusy, setSigBusy] = useState(false);
  const [sigBlob, setSigBlob] = useState<string | null>(null);

  // Re-fetch + render the signature preview whenever the "has signature"
  // flag flips. Uses the bearer token so the image isn't served as an
  // unauthenticated public URL.
  useEffect(() => {
    if (!me?.has_signature || !token) {
      setSigBlob(null);
      return;
    }
    let cancelled = false;
    let created: string | null = null;
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/api/v1/auth/me/signature`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!r.ok) return;
        const blob = await r.blob();
        created = URL.createObjectURL(blob);
        if (!cancelled) setSigBlob(created);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [me?.has_signature, token]);

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

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwErr(null);
    setPwInfo(null);
    if (pwForm.next !== pwForm.confirm) {
      setPwErr('New password and confirmation do not match.');
      return;
    }
    if (pwForm.next.length < 8) {
      setPwErr('New password must be at least 8 characters.');
      return;
    }
    setPwBusy(true);
    try {
      await api('/api/v1/auth/change-password', {
        method: 'POST',
        body: { current_password: pwForm.current, new_password: pwForm.next },
      });
      setPwInfo('Password updated. Use your new password next time you sign in.');
      setPwForm({ current: '', next: '', confirm: '' });
    } catch (ex) {
      setPwErr((ex as ApiError).message);
    } finally {
      setPwBusy(false);
    }
  }

  async function uploadSignature(file: File) {
    setSigErr(null);
    setSigInfo(null);
    setSigBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch(`${API_BASE}/api/v1/auth/me/signature`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: fd,
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail || `Upload failed (${r.status})`);
      }
      setSigInfo('Signature saved. It will appear on the printed case form.');
      refreshMe();
    } catch (ex) {
      setSigErr((ex as Error).message);
    } finally {
      setSigBusy(false);
      if (sigInputRef.current) sigInputRef.current.value = '';
    }
  }

  async function removeSignature() {
    if (!confirm('Remove your signature image?')) return;
    setSigErr(null);
    setSigInfo(null);
    setSigBusy(true);
    try {
      await api('/api/v1/auth/me/signature', { method: 'DELETE' });
      setSigInfo('Signature removed.');
      refreshMe();
    } catch (ex) {
      setSigErr((ex as ApiError).message);
    } finally {
      setSigBusy(false);
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

      {/* -------- Change Password -------- */}
      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          <KeyRound className="h-4 w-4" /> Change Password
        </h2>
        {pwErr && (
          <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
            {pwErr}
          </div>
        )}
        {pwInfo && (
          <div className="mb-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
            {pwInfo}
          </div>
        )}
        <form className="grid grid-cols-1 gap-3 md:grid-cols-3" onSubmit={changePassword}>
          <PwField
            label="Current password"
            autoComplete="current-password"
            value={pwForm.current}
            onChange={(v) => setPwForm({ ...pwForm, current: v })}
            required
          />
          <PwField
            label="New password"
            autoComplete="new-password"
            value={pwForm.next}
            onChange={(v) => setPwForm({ ...pwForm, next: v })}
            required
          />
          <PwField
            label="Confirm new password"
            autoComplete="new-password"
            value={pwForm.confirm}
            onChange={(v) => setPwForm({ ...pwForm, confirm: v })}
            required
          />
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={pwBusy || !pwForm.current || !pwForm.next || !pwForm.confirm}
              className="rounded-md bg-pug-navy-700 px-3 py-2 text-sm font-semibold text-white hover:bg-pug-navy-600 disabled:opacity-50"
            >
              {pwBusy ? 'Saving...' : 'Update Password'}
            </button>
            <p className="mt-2 text-[11px] text-[rgb(var(--color-muted))]">
              Minimum 8 characters. Must be different from your current password.
            </p>
          </div>
        </form>
      </section>

      {/* -------- Signature -------- */}
      <section className="rounded-xl border border-[rgb(var(--color-border))] bg-[rgb(var(--color-card))] p-5 shadow-soft">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-pug-gold-700 dark:text-pug-gold-400">
          <PenLine className="h-4 w-4" /> Signature
        </h2>
        <p className="mb-3 text-xs text-[rgb(var(--color-muted))]">
          Upload an image of your signature (PNG, JPG, GIF or WebP). It will be
          embedded above your name on every printed case form where you are
          listed as a signatory.
        </p>
        {sigErr && (
          <div className="mb-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-300">
            {sigErr}
          </div>
        )}
        {sigInfo && (
          <div className="mb-3 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="-mt-0.5 mr-1 inline h-4 w-4" />
            {sigInfo}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex h-24 w-48 items-center justify-center rounded-md border border-dashed border-[rgb(var(--color-border))] bg-[rgb(var(--color-bg))]">
            {sigBlob ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={sigBlob} alt="Your signature" className="max-h-full max-w-full object-contain" />
            ) : (
              <span className="text-xs text-[rgb(var(--color-muted))]">No signature uploaded</span>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <input
              ref={sigInputRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadSignature(f);
              }}
            />
            <button
              type="button"
              onClick={() => sigInputRef.current?.click()}
              disabled={sigBusy}
              className="inline-flex items-center gap-2 rounded-md bg-pug-gold-500 px-3 py-2 text-sm font-semibold text-pug-navy-800 hover:bg-pug-gold-400 disabled:opacity-50"
            >
              <Upload className="h-4 w-4" /> {me?.has_signature ? 'Replace Signature' : 'Upload Signature'}
            </button>
            {me?.has_signature && (
              <button
                type="button"
                onClick={removeSignature}
                disabled={sigBusy}
                className="inline-flex items-center gap-2 rounded-md border border-rose-500/40 px-3 py-2 text-sm text-rose-600 hover:bg-rose-500/10 disabled:opacity-50"
              >
                <Trash2 className="h-4 w-4" /> Remove
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function PwField({
  label,
  value,
  onChange,
  required,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-[rgb(var(--color-muted))]">
        {label}
      </span>
      <input
        type="password"
        required={required}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[rgb(var(--color-border))] bg-transparent px-3 py-2 text-sm focus:border-pug-gold-500 focus:outline-none"
      />
    </label>
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
