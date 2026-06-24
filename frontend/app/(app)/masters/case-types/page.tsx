'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';

export default function CaseTypesPage() {
  const me = useAuthStore((s) => s.me);
  return (
    <CrudPage
      title="Case Types"
      resource="/api/v1/masters/case-types"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{ code: '', name: '', description: '', is_active: true }}
      fields={[
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Name', required: true },
        { name: 'description', label: 'Description' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'description', label: 'Description' },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
