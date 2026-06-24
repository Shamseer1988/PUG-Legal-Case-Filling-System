'use client';

import { Users } from 'lucide-react';
import { useState } from 'react';
import { CrudPage } from '@/components/CrudPage';
import { CustomerPartnersModal } from '@/components/CustomerPartnersModal';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';

export default function CustomersPage() {
  const me = useAuthStore((s) => s.me);
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');
  const salesmen = useMasterOptions('/api/v1/masters/salesmen', 'name');
  const canWriteMasters = hasPermission(me, 'masters:write');
  const [partnersFor, setPartnersFor] = useState<{ id: number; name: string } | null>(
    null,
  );

  return (
    <>
      <CrudPage
        title="Customers"
        resource="/api/v1/masters/customers"
        canWrite={canWriteMasters}
        emptyTemplate={{
          code: '',
          name: '',
          customer_type: 'Retail',
          phone: '',
          email: '',
          address: '',
          division_id: null,
          salesman_id: null,
          is_active: true,
        }}
        fields={[
          { name: 'code', label: 'Code', required: true },
          { name: 'name', label: 'Name', required: true },
          {
            name: 'customer_type',
            label: 'Type',
            type: 'select',
            options: [
              { value: 'Retail', label: 'Retail' },
              { value: 'Distribution', label: 'Distribution' },
              { value: 'Corporate', label: 'Corporate' },
            ],
          },
          { name: 'phone', label: 'Phone' },
          { name: 'email', label: 'Email', type: 'email' },
          { name: 'address', label: 'Address' },
          {
            name: 'division_id',
            label: 'Division',
            type: 'select',
            options: divisions,
            allowEmpty: true,
          },
          {
            name: 'salesman_id',
            label: 'Salesman',
            type: 'select',
            options: salesmen,
            allowEmpty: true,
          },
          { name: 'is_active', label: 'Active', type: 'checkbox' },
        ]}
        columns={[
          { key: 'code', label: 'Code' },
          { key: 'name', label: 'Name' },
          { key: 'customer_type', label: 'Type' },
          {
            key: 'division_id',
            label: 'Division',
            render: (v) => divisions.find((d) => d.value === v)?.label ?? '-',
          },
          {
            key: 'salesman_id',
            label: 'Salesman',
            render: (v) => salesmen.find((s) => s.value === v)?.label ?? '-',
          },
          { key: 'is_active', label: 'Active', render: (v) => (v ? 'Yes' : 'No') },
        ]}
        rowActions={(row) => (
          <button
            onClick={() =>
              setPartnersFor({ id: row.id, name: String(row.name ?? `#${row.id}`) })
            }
            className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
            title="Manage partners (cheque signatories, authorised signatories, etc.)"
          >
            <Users className="h-3 w-3" /> Partners
          </button>
        )}
      />

      {partnersFor && (
        <CustomerPartnersModal
          customerId={partnersFor.id}
          customerName={partnersFor.name}
          canWrite={canWriteMasters}
          onClose={() => setPartnersFor(null)}
        />
      )}
    </>
  );
}
