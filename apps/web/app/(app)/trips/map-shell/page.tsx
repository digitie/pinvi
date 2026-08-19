import { MapView } from '@/components/map/MapView';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md
 * 전체 화면 지도 — 높이는 셸이 흘려보낸다(flex-1 min-h-0), 100dvh 상수 금지.
 */

export default function TripMapShellPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-hairline pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">지도</h1>
        </div>
      </header>
      <section className="flex min-h-[320px] flex-1 flex-col">
        <MapView apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''} className="flex-1" />
      </section>
    </div>
  );
}
