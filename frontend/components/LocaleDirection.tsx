'use client';

import { useEffect } from 'react';
import { isRtl, useLocale } from '@/lib/i18n';

/** Tracks the user's preferred locale and reflects it on the
 *  document so RTL stylesheets / utilities kick in app-wide.
 *
 *  Mounting this component once at the top of (app)/layout.tsx
 *  is enough; it doesn't render anything of its own. */
export function LocaleDirection() {
  const locale = useLocale();
  useEffect(() => {
    const rtl = isRtl(locale);
    const html = document.documentElement;
    html.lang = locale;
    html.dir = rtl ? 'rtl' : 'ltr';
    return () => {
      // Don't leave a stale dir hanging on the html element when
      // the (app) tree unmounts (e.g. on /login). Default back
      // to LTR so the login screen renders normally.
      html.dir = 'ltr';
      html.lang = 'en';
    };
  }, [locale]);
  return null;
}
