import { MapView } from '@/components/map/MapView';

export default function TripMapShellPage() {
  return (
    <div className="flex min-h-[calc(100dvh-120px)] flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-hairline pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">지도</h1>
        </div>
      </header>
      <section className="min-h-[520px] flex-1">
        <MapView apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''} className="h-full" />
      </section>
    </div>
  );
}
