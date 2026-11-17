import { FeatureMapView } from '@/components/map/FeatureMapView';
import { parseSuggestParam } from '@pinvi/domain';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md
 * 전체 화면 지도(소유자 요청 2026-11-17) — 셸(AppShell `/map` 분기)이 창 높이를 고정하고 본문 여백을 없앤다.
 * 높이는 셸이 흘려보낸다(flex-1 min-h-0), 100dvh 상수 금지. 제목·설명 줄은 지도 몫을 먹으므로 화면에서
 * 숨기고 읽기 도구용 제목(h1 1개, CORE-027)만 남긴다. 검색·레이어·내 위치는 지도 위 오버레이다.
 */

export default async function ExploreMapPage({
  searchParams,
}: {
  searchParams: Promise<{ suggest?: string | string[] }>;
}) {
  const suggestCoord = parseSuggestParam((await searchParams).suggest);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <h1 className="sr-only">탐색 지도</h1>
      <p className="sr-only">지도를 움직이면 화면 범위의 장소·이벤트·공지를 불러옵니다.</p>
      <FeatureMapView
        apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''}
        className="min-h-0 flex-1"
        initialSuggestCoord={suggestCoord}
      />
    </div>
  );
}
