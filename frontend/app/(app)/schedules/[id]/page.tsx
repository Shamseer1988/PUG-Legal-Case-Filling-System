'use client';

import { useParams } from 'next/navigation';
import { ScheduleForm } from '@/components/ScheduleForm';

export default function ScheduleDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  if (!id) return <div className="p-4 text-sm">Invalid schedule id.</div>;
  return <ScheduleForm scheduleId={id} />;
}
