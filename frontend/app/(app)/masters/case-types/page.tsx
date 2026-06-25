'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useT } from '@/lib/i18n';

export default function CaseTypesPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  return (
    <CrudPage
      title={t('masters.case_types.title')}
      resource="/api/v1/masters/case-types"
      canWrite={hasPermission(me, 'masters:write')}
      emptyTemplate={{ code: '', name: '', description: '', is_active: true }}
      fields={[
        { name: 'code', label: t('masters.col.code'), required: true },
        { name: 'name', label: t('masters.col.name'), required: true },
        { name: 'description', label: t('masters.col.description') },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: t('masters.col.code') },
        { key: 'name', label: t('masters.col.name') },
        { key: 'description', label: t('masters.col.description') },
        { key: 'is_active', label: t('common.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
      ]}
    />
  );
}
