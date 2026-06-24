'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';

export default function BanksPage() {
  const me = useAuthStore((s) => s.me);
  return (
    <CrudPage
      title="Banks"
      resource="/api/v1/masters/banks"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{ code: '', name: '', is_active: true }}
      fields={[
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Bank Name', required: true },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Bank Name' },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
