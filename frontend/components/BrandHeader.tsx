'use client';

import { useState } from 'react';
import { API_BASE } from '@/lib/api';
import { ThemeToggle } from './ThemeToggle';

export function BrandHeader() {
  const [logoErr, setLogoErr] = useState(false);

  return (
    <header className="border-b-4 border-pug-gold-500 bg-gradient-to-br from-pug-navy-800 via-pug-navy-600 to-pug-navy-500 text-white">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-5">
        {logoErr ? (
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-pug-gold-500 font-extrabold text-pug-navy-800 shadow-gold">
            PUG
          </div>
        ) : (
          <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full border border-white/20 bg-white/10 shadow-gold">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE}/api/v1/settings/public/logo`}
              alt="Logo"
              className="h-full w-full object-cover"
              onError={() => setLogoErr(true)}
            />
          </div>
        )}
        <div className="flex flex-col">
          <span className="text-xs font-semibold uppercase tracking-widest text-pug-gold-300">
            Paris United Group Holding
          </span>
          <h1 className="text-lg font-semibold leading-tight">
            Legal Case Control System
          </h1>
        </div>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
