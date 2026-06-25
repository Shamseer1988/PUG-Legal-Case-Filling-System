'use client';

import { Users } from 'lucide-react';
import { useState } from 'react';
import { CrudPage } from '@/components/CrudPage';
import { CustomerPartnersModal } from '@/components/CustomerPartnersModal';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useMasterOptions } from '@/lib/useMasters';
import { useT } from '@/lib/i18n';

export default function CustomersPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  const divisions = useMasterOptions('/api/v1/masters/divisions', 'name');
  const salesmen = useMasterOptions('/api/v1/masters/salesmen', 'name');
  const canWriteMasters = hasPermission(me, 'masters:write');
  // Accountants get create-only access limited to their own division
  const canCreateOwn = !canWriteMasters && hasPermission(me, 'masters:create_own_division');
  const accountantDivId = canCreateOwn ? (me?.divisions?.[0] ?? null) : null;
  const [partnersFor, setPartnersFor] = useState<{ id: number; name: string } | null>(
    null,
  );

  return (
    <>
      <CrudPage
        title={t('customers.title')}
        resource="/api/v1/masters/customers"
        canWrite={canWriteMasters}
        canCreate={canCreateOwn}
        emptyTemplate={{
          code: '',
          name: '',
          customer_type: 'Retail',
          phone: '',
          email: '',
          address: '',
          division_id: accountantDivId,
          salesman_id: null,
          is_active: true,
        }}
        fields={[
          { name: 'code', label: t('customers.col.code'), required: true },
          { name: 'name', label: t('customers.col.name'), required: true },
          {
            name: 'customer_type',
            label: t('customers.col.type'),
            type: 'select',
            options: [
              { value: 'Retail', label: 'Retail' },
              { value: 'Distribution', label: 'Distribution' },
              { value: 'Corporate', label: 'Corporate' },
            ],
          },
          { name: 'phone', label: t('customers.col.phone') },
          { name: 'email', label: t('customers.col.email'), type: 'email' },
          { name: 'address', label: t('customers.col.address') },
          {
            name: 'division_id',
            label: t('customers.col.division'),
            type: 'select',
            options: divisions,
            allowEmpty: !canCreateOwn,
            disabled: canCreateOwn,
          },
          {
            name: 'salesman_id',
            label: t('customers.col.salesman'),
            type: 'select',
            options: salesmen,
            allowEmpty: true,
          },
          { name: 'is_active', label: t('customers.col.active'), type: 'checkbox' },
        ]}
        columns={[
          { key: 'code', label: t('customers.col.code') },
          { key: 'name', label: t('customers.col.name') },
          { key: 'customer_type', label: t('customers.col.type') },
          {
            key: 'division_id',
            label: t('customers.col.division'),
            render: (v) => divisions.find((d) => d.value === v)?.label ?? '-',
          },
          {
            key: 'salesman_id',
            label: t('customers.col.salesman'),
            render: (v) => salesmen.find((s) => s.value === v)?.label ?? '-',
          },
          { key: 'is_active', label: t('customers.col.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
        ]}
        rowActions={(row) => (
          <button
            onClick={() =>
              setPartnersFor({ id: row.id, name: String(row.name ?? `#${row.id}`) })
            }
            className="mr-2 inline-flex items-center gap-1 rounded px-2 py-1 text-xs hover:bg-[rgb(var(--color-border))]/40"
            title={t('customers.col.partners')}
          >
            <Users className="h-3 w-3" /> {t('customers.col.partners')}
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
