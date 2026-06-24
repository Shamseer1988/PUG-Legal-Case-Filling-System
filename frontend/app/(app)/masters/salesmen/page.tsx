'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';

export default function SalesmenPage() {
  const me = useAuthStore((s) => s.me);
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');

  return (
    <CrudPage
      title="Salesmen"
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
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Name', required: true },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        {
          name: 'division_id',
          label: 'Division',
          type: 'select',
          options: divisions,
          allowEmpty: true,
        },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'email', label: 'Email' },
        {
          key: 'division_id',
          label: 'Division',
          render: (v) => divisions.find((d) => d.value === v)?.label ?? '-',
        },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
