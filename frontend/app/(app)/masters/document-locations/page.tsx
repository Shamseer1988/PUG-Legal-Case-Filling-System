'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';

export default function DocumentLocationsPage() {
  const me = useAuthStore((s) => s.me);
  return (
    <CrudPage
      title="Document Locations"
      resource="/api/v1/masters/document-locations"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{
        code: '',
        name: '',
        description: '',
        is_storage: true,
        is_active: true,
      }}
      fields={[
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Name', required: true },
        { name: 'description', label: 'Description / where to find it' },
        {
          name: 'is_storage',
          label: 'Counts as storage (overdue report ignores docs parked here)',
          type: 'checkbox',
        },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'description', label: 'Description' },
        { key: 'is_storage', label: 'Storage', render: (v) => (v ? 'Yes' : 'No') },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
