import { MapView } from '@/components/map/MapView';

export default function TripMapShellPage() {
  return (
    <div className="flex min-h-[calc(100vh-120px)] flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-hairline pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-primary">TripMate</p>
          <h1 className="mt-1 text-2xl font-bold text-ink md:text-3xl">지도</h1>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs text-muted">
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">서울</span>
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">VWorld</span>
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">Shell</span>
        </div>
      </header>
      <section className="min-h-[520px] flex-1">
        <MapView apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''} className="h-full" />
      </section>
    </div>
  );
}
