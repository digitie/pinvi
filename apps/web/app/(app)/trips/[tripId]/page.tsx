'use client';

import { useParams } from 'next/navigation';
import { TripDetail } from '@/components/trips/TripDetail';

export default function TripDetailPage() {
  const params = useParams<{ tripId: string }>();
  return <TripDetail tripId={params.tripId} />;
}
