'use client';

import { useParams } from 'next/navigation';
import { NoticePlanEditor } from '@/components/admin/NoticePlanEditor';

export default function AdminNoticePlanDetailPage() {
  const params = useParams<{ planId: string }>();
  return <NoticePlanEditor planId={params.planId} />;
}
