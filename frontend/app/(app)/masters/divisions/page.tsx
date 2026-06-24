'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';

export default function DivisionsPage() {
  const me = useAuthStore((s) => s.me);
  return (
    <CrudPage
      title="Divisions"
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
        { name: 'code', label: 'Code', required: true },
        { name: 'name', label: 'Name', required: true },
        { name: 'address', label: 'Address' },
        { name: 'accountant_email', label: 'Accountant Email', type: 'email' },
        { name: 'manager_email', label: 'Manager Email', type: 'email' },
        { name: 'sales_manager_email', label: 'Sales Manager Email', type: 'email' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Name' },
        { key: 'manager_email', label: 'Manager Email' },
        {
          key: 'is_active',
          label: 'Active',
          render: (v) => (v ? 'Yes' : 'No'),
        },
      ]}
    />
  );
}
