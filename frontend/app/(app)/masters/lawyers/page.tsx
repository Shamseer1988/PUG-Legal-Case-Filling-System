'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';

export default function LawyersPage() {
  const me = useAuthStore((s) => s.me);
  const divisions = useMasterOptions('/api/v1/masters/divisions');

  return (
    <CrudPage
      title="Lawyers"
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
        { name: 'name', label: 'Name', required: true },
        { name: 'firm', label: 'Firm' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
        {
          name: 'division_ids',
          label: 'Divisions',
          type: 'divisions',
          allField: 'is_all_divisions',
          allLabel: 'All Companies',
          options: divisions,
        },
      ]}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'firm', label: 'Firm' },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        {
          key: 'is_all_divisions',
          label: 'Divisions',
          render: (v, row) => {
            if (v) return 'All Companies';
            const ids = (row.division_ids as number[] | undefined) ?? [];
            if (ids.length === 0) return '-';
            const names = ids
              .map((id) => divisions.find((d) => d.value === id)?.label ?? `#${id}`)
              .join(', ');
            return names;
          },
        },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
