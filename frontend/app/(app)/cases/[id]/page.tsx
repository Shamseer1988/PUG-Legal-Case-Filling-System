'use client';

import { useParams } from 'next/navigation';
import { CaseForm } from '@/components/CaseForm';

export default function CaseDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  if (!id) return <div className="p-4 text-sm">Invalid case id.</div>;
  return <CaseForm caseId={id} />;
}
