import { FeatureMapView } from '@/components/map/FeatureMapView';
import { parseSuggestParam } from '@pinvi/domain';

export default async function ExploreMapPage({
  searchParams,
}: {
  searchParams: Promise<{ suggest?: string | string[] }>;
}) {
  const suggestCoord = parseSuggestParam((await searchParams).suggest);
  return (
    <div className="flex min-h-[calc(100vh-120px)] flex-col gap-4">
      <header className="flex flex-col gap-3 border-b border-hairline pb-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-primary">Pinvi</p>
          <h1 className="mt-1 text-2xl font-bold text-ink md:text-3xl">탐색 지도</h1>
          <p className="mt-1 text-sm text-muted">
            지도를 움직이면 화면 범위의 장소·이벤트·공지를 불러옵니다.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-xs text-muted">
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">VWorld</span>
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">features</span>
          <span className="rounded-sm border border-hairline bg-canvas px-3 py-2">cluster</span>
        </div>
      </header>
      <section className="min-h-[520px] flex-1">
        <FeatureMapView
          apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''}
          className="h-full"
          initialSuggestCoord={suggestCoord}
        />
      </section>
    </div>
  );
}
