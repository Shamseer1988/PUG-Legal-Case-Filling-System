'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useT } from '@/lib/i18n';

export default function BanksPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  return (
    <CrudPage
      title={t('masters.banks.title')}
      resource="/api/v1/masters/banks"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{ code: '', name: '', is_active: true }}
      fields={[
        { name: 'code', label: t('masters.col.code'), required: true },
        { name: 'name', label: t('masters.col.bank_name'), required: true },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: t('masters.col.code') },
        { key: 'name', label: t('masters.col.bank_name') },
        { key: 'is_active', label: t('common.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
      ]}
    />
  );
}
