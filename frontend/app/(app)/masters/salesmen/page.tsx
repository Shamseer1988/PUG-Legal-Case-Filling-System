'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';
import { useT } from '@/lib/i18n';

export default function SalesmenPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');

  return (
    <CrudPage
      title={t('masters.salesmen.title')}
      resource="/api/v1/masters/salesmen"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{
        code: '',
        name: '',
        email: '',
        phone: '',
        division_id: null,
        is_active: true,
      }}
      fields={[
        { name: 'code', label: t('masters.col.code'), required: true },
        { name: 'name', label: t('masters.col.name'), required: true },
        { name: 'email', label: t('masters.col.email'), type: 'email' },
        { name: 'phone', label: t('masters.col.phone') },
        {
          name: 'division_id',
          label: t('masters.col.division'),
          type: 'select',
          options: divisions,
          allowEmpty: true,
        },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: t('masters.col.code') },
        { key: 'name', label: t('masters.col.name') },
        { key: 'email', label: t('masters.col.email') },
        {
          key: 'division_id',
          label: t('masters.col.division'),
          render: (v) => divisions.find((d) => d.value === v)?.label ?? '-',
        },
        { key: 'is_active', label: t('common.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
      ]}
    />
  );
}
