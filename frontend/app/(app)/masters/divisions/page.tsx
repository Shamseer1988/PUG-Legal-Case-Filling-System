'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useT } from '@/lib/i18n';

export default function DivisionsPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  return (
    <CrudPage
      title={t('masters.divisions.title')}
      resource="/api/v1/masters/divisions"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{
        code: '',
        name: '',
        address: '',
        accountant_email: '',
        manager_email: '',
        sales_manager_email: '',
        is_active: true,
      }}
      fields={[
        { name: 'code', label: t('masters.col.code'), required: true },
        { name: 'name', label: t('masters.col.name'), required: true },
        { name: 'address', label: t('masters.col.address') },
        { name: 'accountant_email', label: t('masters.col.accountant_email'), type: 'email' },
        { name: 'manager_email', label: t('masters.col.manager_email'), type: 'email' },
        { name: 'sales_manager_email', label: t('masters.col.sales_manager_email'), type: 'email' },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: t('masters.col.code') },
        { key: 'name', label: t('masters.col.name') },
        { key: 'manager_email', label: t('masters.col.manager_email') },
        {
          key: 'is_active',
          label: t('common.active'),
          render: (v) => (v ? t('common.yes') : t('common.no')),
        },
      ]}
    />
  );
}
