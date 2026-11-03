import { ButtonLink } from '@/components/ui/Button';
import { TripDashboard } from '@/components/trips/TripDashboard';

export default function TripsPage() {
  return <div className="space-y-3"><div className="flex justify-end"><ButtonLink href="/trips/trash" variant="ghost">휴지통</ButtonLink></div><TripDashboard /></div>;
}
