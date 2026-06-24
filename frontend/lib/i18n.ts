'use client';

import { useAuthStore } from './auth';

/** Minimal i18n helper for Phase 31.
 *
 * A full next-intl migration would touch every page; instead this
 * gives us a typed ``t(key)`` function backed by a static EN+AR
 * message catalog plus a ``useLocale()`` hook that reads the
 * signed-in user's preferred language. UI strings that aren't
 * translated yet just render in English; that way new bundles can
 * land incrementally without breaking anything.
 */

export type Locale = 'en' | 'ar';

export const DEFAULT_LOCALE: Locale = 'en';
export const SUPPORTED_LOCALES: Locale[] = ['en', 'ar'];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  ar: 'العربية',
};

// Translation catalog. Keep alphabetical inside each section. Add
// new keys to BOTH languages — the AR side is allowed to fall
// back to EN if a key is missing, but missing keys should be
// rare.
const MESSAGES: Record<Locale, Record<string, string>> = {
  en: {
    // Sidebar group titles
    'sidebar.workspace': 'Workspace',
    'sidebar.transactions': 'Transactions',
    'sidebar.insights': 'Insights',
    'sidebar.masters': 'Masters',
    'sidebar.admin': 'Admin',

    // Sidebar items
    'sidebar.dashboard': 'Dashboard',
    'sidebar.profile': 'My Profile',
    'sidebar.cases': 'Cases',
    'sidebar.approvals': 'Approvals Inbox',
    'sidebar.hearings': 'Hearings Calendar',
    'sidebar.cash_requests': 'Cash Requests',
    'sidebar.reports': 'Reports',
    'sidebar.scheduled_reports': 'Scheduled Reports',
    'sidebar.signout': 'Sign out',

    // Common buttons
    'btn.save': 'Save',
    'btn.cancel': 'Cancel',
    'btn.delete': 'Delete',
    'btn.edit': 'Edit',
    'btn.new': 'New',
    'btn.search': 'Search',

    // Profile - locale section
    'profile.language': 'Language',
    'profile.language.help':
      'Pick the language for the interface and the notification emails sent to you.',
    'profile.language.saved': 'Language preference saved.',
  },
  ar: {
    // Sidebar group titles
    'sidebar.workspace': 'مساحة العمل',
    'sidebar.transactions': 'المعاملات',
    'sidebar.insights': 'التقارير والإحصاءات',
    'sidebar.masters': 'البيانات الرئيسية',
    'sidebar.admin': 'الإدارة',

    // Sidebar items
    'sidebar.dashboard': 'لوحة التحكم',
    'sidebar.profile': 'ملفي الشخصي',
    'sidebar.cases': 'القضايا',
    'sidebar.approvals': 'صندوق الموافقات',
    'sidebar.hearings': 'تقويم الجلسات',
    'sidebar.cash_requests': 'طلبات المصاريف',
    'sidebar.reports': 'التقارير',
    'sidebar.scheduled_reports': 'التقارير المجدولة',
    'sidebar.signout': 'تسجيل الخروج',

    // Common buttons
    'btn.save': 'حفظ',
    'btn.cancel': 'إلغاء',
    'btn.delete': 'حذف',
    'btn.edit': 'تعديل',
    'btn.new': 'جديد',
    'btn.search': 'بحث',

    // Profile
    'profile.language': 'اللغة',
    'profile.language.help':
      'اختر لغة الواجهة ولغة رسائل الإشعارات التي تصلك بالبريد الإلكتروني.',
    'profile.language.saved': 'تم حفظ تفضيل اللغة.',
  },
};

export function useLocale(): Locale {
  const me = useAuthStore((s) => s.me);
  const raw = (me?.locale ?? DEFAULT_LOCALE) as Locale;
  return SUPPORTED_LOCALES.includes(raw) ? raw : DEFAULT_LOCALE;
}

export function isRtl(locale: Locale): boolean {
  return locale === 'ar';
}

/** Lookup a translation. Falls back to the English value, then to
 *  the key itself so missing strings are visible (and fixable). */
export function tFor(locale: Locale, key: string): string {
  return MESSAGES[locale]?.[key] ?? MESSAGES.en[key] ?? key;
}

/** Translate-in-the-component hook. */
export function useT(): (key: string) => string {
  const locale = useLocale();
  return (key: string) => tFor(locale, key);
}
