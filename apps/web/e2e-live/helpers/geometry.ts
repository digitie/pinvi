/** MapLibre의 실제 layer/source/hit/camera를 읽는 live 검증용 helper. 제품 API를 대체하지 않는다. */
import { expect, type JSHandle, type Page } from '@playwright/test';
import type { MapLibreMap } from 'vworld-map-web';

export async function renderedMap(page: Page): Promise<JSHandle<MapLibreMap>> {
  // 설치된 vworld-map-web의 MapStore provider를 읽는다. 앱에 전역 debug 핸들을 추가하지 않는다.
  return (await page.waitForFunction(
    () => {
      const element = document.querySelector('.maplibregl-map');
      if (!element) return null;
      type Fiber = {
        memoizedProps?: { value?: { getSnapshot?: () => { map?: MapLibreMap } } };
        return?: Fiber;
      };
      const record = element as unknown as Record<string, unknown>;
      const key = Object.keys(record).find((name) => name.startsWith('__reactFiber'));
      let fiber = key ? (record[key] as Fiber | undefined) : undefined;
      while (fiber) {
        const store = fiber.memoizedProps?.value;
        const map = store?.getSnapshot?.()?.map;
        if (map?.getCanvas) return map;
        fiber = fiber.return;
      }
      return null;
    },
    undefined,
    { timeout: 30_000 },
  )) as JSHandle<MapLibreMap>;
}

export async function waitForGeometry(
  map: JSHandle<MapLibreMap>,
  featureId: string,
): Promise<void> {
  await expect
    .poll(
      async () =>
        await map.evaluate((m, id) => {
          const prefix = 'pinvi-geometry-' + encodeURIComponent(id);
          return Boolean(m.getSource(prefix + '-source') && m.isSourceLoaded(prefix + '-source'));
        }, featureId),
    )
    .toBe(true);
}

/** 실제 target 도형의 hit를 찾고 최상단 도형을 캔버스 클릭한다. DOM 목록은 사용하지 않는다. */
export async function clickRenderedGeometry(
  page: Page,
  map: JSHandle<MapLibreMap>,
  featureId: string,
): Promise<string> {
  await waitForGeometry(map, featureId);
  const hit = await map.evaluate((m, id) => {
    const canvas = m.getCanvas(),
      rect = canvas.getBoundingClientRect();
    const layers = m
      .getStyle()
      .layers.filter((layer) => layer.id.startsWith('pinvi-geometry-'))
      .map((layer) => layer.id);
    const rendered = m
      .queryRenderedFeatures({ layers })
      .filter((feature) => feature.properties.feature_id === id);
    const candidates: [number, number][] = [];
    const add = (value: unknown): void => {
      if (!Array.isArray(value)) return;
      if (typeof value[0] === 'number' && typeof value[1] === 'number') {
        const p = m.project([value[0], value[1]]);
        candidates.push([p.x, p.y]);
        return;
      }
      value.forEach(add);
      for (let i = 1; i < value.length; i++) {
        const a = value[i - 1],
          b = value[i];
        if (
          Array.isArray(a) &&
          Array.isArray(b) &&
          typeof a[0] === 'number' &&
          typeof b[0] === 'number'
        ) {
          const p = m.project([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
          candidates.push([p.x, p.y]);
        }
      }
    };
    for (const feature of rendered)
      if ('coordinates' in feature.geometry) add(feature.geometry.coordinates);
    // polygon 내부와 현재 viewport로 잘린 긴 선도 확인한다.
    for (let y = 12; y < rect.height - 12; y += 12)
      for (let x = 12; x < rect.width - 12; x += 12) candidates.push([x, y]);
    // 같은 이름의 구간들이 끝점·겹친 선을 공유한다(예: '설악산_대청봉' 여러 feature). 겹친 점을
    // 누르면 앱과 helper의 최상단 판정이 반 픽셀 차이로 갈릴 수 있으므로, 대상만 걸리는 정수
    // 픽셀을 먼저 고른다. 없을 때만 대상이 포함된 점의 최상단 feature를 기대값으로 쓴다.
    let fallback: { x: number; y: number; id: string } | null = null;
    for (const [rawX, rawY] of candidates) {
      const x = Math.round(rawX),
        y = Math.round(rawY);
      if (x < 4 || y < 4 || x > rect.width - 4 || y > rect.height - 4) continue;
      if (document.elementFromPoint(rect.left + x, rect.top + y) !== canvas) continue;
      const hits = m.queryRenderedFeatures([x, y], { layers });
      if (!hits.some((feature) => feature.properties.feature_id === id)) continue;
      if (hits.every((feature) => feature.properties.feature_id === id))
        return { x: rect.left + x, y: rect.top + y, id };
      const top = hits[0];
      if (top && !fallback)
        fallback = { x: rect.left + x, y: rect.top + y, id: String(top.properties.feature_id) };
    }
    return fallback;
  }, featureId);
  expect(hit, '실제 canvas에 요청한 feature의 rendered hit가 있어야 한다').not.toBeNull();
  await page.mouse.click(hit!.x, hit!.y);
  await expect(page.getByTestId('geometry-popup')).toHaveAttribute('data-feature-id', hit!.id);
  return hit!.id;
}

export async function waitForCamera(map: JSHandle<MapLibreMap>): Promise<void> {
  await map.evaluate(async (m) => {
    if (m.isMoving()) await new Promise<void>((resolve) => m.once('moveend', () => resolve()));
  });
}

export async function expectGeometryRemoved(
  map: JSHandle<MapLibreMap>,
  ids: string[],
): Promise<void> {
  await expect
    .poll(
      async () =>
        await map.evaluate(
          (m, ids) =>
            ids.every((id) => {
              const prefix = 'pinvi-geometry-' + encodeURIComponent(id);
              return (
                !m.getSource(prefix + '-source') &&
                !m.getLayer(prefix + '-layer') &&
                !m.getLayer(prefix + '-fill-layer') &&
                !m.getLayer(prefix + '-line-layer')
              );
            }),
          ids,
        ),
    )
    .toBe(true);
}

export async function openGeometryDetail(
  page: Page,
  featureId: string,
  kind: 'route' | 'area',
): Promise<void> {
  const response = page.waitForResponse((res) => {
    const url = new URL(res.url());
    return (
      res.request().method() === 'GET' &&
      url.pathname.endsWith('/features/' + encodeURIComponent(featureId) + '/detail-card') &&
      !url.searchParams.has('providers')
    );
  });
  await page.getByTestId('geometry-detail-open').click();
  const res = await response;
  expect(res.status(), 'geometry 상세 HTTP 성공').toBe(200);
  const envelope = (await res.json()) as { data?: { feature_id?: unknown; kind?: unknown } };
  expect(envelope.data?.feature_id).toBe(featureId);
  expect(envelope.data?.kind).toBe(kind);
  const body = page.getByTestId('feature-detail-card-body');
  await expect(body).toBeVisible();
  await expect(body).toHaveAttribute('data-kind', kind);
}
