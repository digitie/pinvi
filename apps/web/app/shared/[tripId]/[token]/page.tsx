'use client';

import { useParams } from 'next/navigation';
import { SharedTripView } from '@/components/trips/SharedTripView';

export default function SharedTripPage() {
  const params = useParams<{ tripId: string; token: string }>();
  return (
    <main className="mx-auto min-h-screen w-full max-w-5xl px-4 py-8">
      <SharedTripView tripId={params.tripId} token={params.token} />
    </main>
  );
}
