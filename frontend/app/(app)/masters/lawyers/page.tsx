'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';
import { useT } from '@/lib/i18n';

export default function LawyersPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  const divisions = useMasterOptions('/api/v1/masters/divisions');

  return (
    <CrudPage
      title={t('masters.lawyers.title')}
      resource="/api/v1/masters/lawyers"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{
        name: '',
        firm: '',
        email: '',
        phone: '',
        is_active: true,
        is_all_divisions: false,
        division_ids: [],
      }}
      fields={[
        { name: 'name', label: t('masters.col.name'), required: true },
        { name: 'firm', label: t('masters.col.firm') },
        { name: 'email', label: t('masters.col.email'), type: 'email' },
        { name: 'phone', label: t('masters.col.phone') },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
        {
          name: 'division_ids',
          label: t('masters.col.divisions'),
          type: 'divisions',
          allField: 'is_all_divisions',
          allLabel: t('common.all_companies'),
          options: divisions,
        },
      ]}
      columns={[
        { key: 'name', label: t('masters.col.name') },
        { key: 'firm', label: t('masters.col.firm') },
        { key: 'email', label: t('masters.col.email') },
        { key: 'phone', label: t('masters.col.phone') },
        {
          key: 'is_all_divisions',
          label: t('masters.col.divisions'),
          render: (v, row) => {
            if (v) return t('common.all_companies');
            const ids = (row.division_ids as number[] | undefined) ?? [];
            if (ids.length === 0) return '-';
            const names = ids
              .map((id) => divisions.find((d) => d.value === id)?.label ?? `#${id}`)
              .join(', ');
            return names;
          },
        },
        { key: 'is_active', label: t('common.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
      ]}
    />
  );
}
