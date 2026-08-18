import { FeatureMapView } from '@/components/map/FeatureMapView';
import { parseSuggestParam } from '@pinvi/domain';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md
 * 전체 화면 지도 — 높이는 셸이 흘려보낸다(flex-1 min-h-0), 100dvh 상수 금지.
 */

export default async function ExploreMapPage({
  searchParams,
}: {
  searchParams: Promise<{ suggest?: string | string[] }>;
}) {
  const suggestCoord = parseSuggestParam((await searchParams).suggest);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-hairline pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">탐색 지도</h1>
          <p className="mt-1 text-sm text-muted">
            지도를 움직이면 화면 범위의 장소·이벤트·공지를 불러옵니다.
          </p>
        </div>
      </header>
      <section className="min-h-[320px] flex-1">
        <FeatureMapView
          apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''}
          className="h-full"
          initialSuggestCoord={suggestCoord}
        />
      </section>
    </div>
  );
}
