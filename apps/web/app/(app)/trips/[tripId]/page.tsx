'use client';

import { useParams } from 'next/navigation';
import { TripDetail } from '@/components/trips/TripDetail';

export default function TripDetailPage() {
  const params = useParams<{ tripId: string }>();
  return (
    <div className="min-h-[calc(100vh-120px)]">
      <TripDetail tripId={params.tripId} />
    </div>
  );
}
