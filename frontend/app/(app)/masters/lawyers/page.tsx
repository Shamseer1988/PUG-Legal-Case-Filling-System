'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';

export default function LawyersPage() {
  const me = useAuthStore((s) => s.me);
  return (
    <CrudPage
      title="Lawyers"
      resource="/api/v1/masters/lawyers"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{ name: '', firm: '', email: '', phone: '', is_active: true }}
      fields={[
        { name: 'name', label: 'Name', required: true },
        { name: 'firm', label: 'Firm' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'is_active', label: 'Active', type: 'checkbox' },
      ]}
      columns={[
        { key: 'name', label: 'Name' },
        { key: 'firm', label: 'Firm' },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
      ]}
    />
  );
}
