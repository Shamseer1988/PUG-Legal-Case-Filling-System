'use client';

import { CrudPage } from '@/components/CrudPage';
import { hasPermission, useAuthStore } from '@/lib/auth';
import { useT } from '@/lib/i18n';

export default function DocumentLocationsPage() {
  const me = useAuthStore((s) => s.me);
  const t = useT();
  return (
    <CrudPage
      title={t('masters.document_locations.title')}
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
        { name: 'code', label: t('masters.col.code'), required: true },
        { name: 'name', label: t('masters.col.name'), required: true },
        { name: 'description', label: t('masters.col.description_help') },
        {
          name: 'is_storage',
          label: t('masters.col.is_storage_help'),
          type: 'checkbox',
        },
        { name: 'is_active', label: t('common.active'), type: 'checkbox' },
      ]}
      columns={[
        { key: 'code', label: t('masters.col.code') },
        { key: 'name', label: t('masters.col.name') },
        { key: 'description', label: t('masters.col.description') },
        { key: 'is_storage', label: t('masters.col.storage'), render: (v) => (v ? t('common.yes') : t('common.no')) },
        { key: 'is_active', label: t('common.active'), render: (v) => (v ? t('common.yes') : t('common.no')) },
      ]}
    />
  );
}
