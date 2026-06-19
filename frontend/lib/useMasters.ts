'use client';

import { useEffect, useState } from 'react';
import { api } from './api';

type Option = { value: number; label: string };

export function useMasterOptions(resource: string, labelKey: string = 'name'): Option[] {
  const [opts, setOpts] = useState<Option[]>([]);
  useEffect(() => {
    api<Array<Record<string, unknown>>>(resource)
      .then((rows) =>
        setOpts(
          rows.map((r) => ({
            value: Number(r.id),
            label: String(r[labelKey] ?? r.name ?? r.id),
          })),
        ),
      )
      .catch(() => setOpts([]));
  }, [resource, labelKey]);
  return opts;
}
