/**
 * NEAR area — local helpers shared by the nearby/transport live specs.
 *
 * Everything here is derived from the deployed PinVi UI (main b1cef056, PR #619):
 *   apps/web/components/map/TransportLayerControls.tsx   (chips, state lines, incident list)
 *   apps/web/components/map/TransportMarkers.tsx         (sr-only legend `transport-marker`)
 *   apps/web/components/map/TransportDetailDialog.tsx    (dialog testid prefix `transport-detail`)
 *   apps/web/lib/useTransportLayers.ts                   (request shape, debounce, soft-fail)
 *   packages/domain/src/transport.ts                     (labels, min zoom, freshness label)
 *   packages/api-client/src/endpoints/transport.ts       (paths)
 *
 * No route mocking anywhere (#618 pitfall) — these only observe real requests.
 */
import { expect, type Locator, type Page, type Response } from '@playwright/test';
import { renderedMap, waitForCamera } from './geometry';
import { dismissFeaturePopup } from './live';
import { runSearch, searchRows } from './search';
import { coordinateFixtureIndex } from './searchFixture';

export const LAYERS = ['fuel_station', 'rest_area', 'highway_incident', 'airport'] as const;
export type Layer = (typeof LAYERS)[number];

/** TRANSPORT_LAYER_META — display order, label and min zoom (packages/domain/src/transport.ts). */
export const LAYER_LABEL: Record<Layer, string> = {
  fuel_station: '주유소',
  rest_area: '휴게소',
  highway_incident: '교통 돌발',
  airport: '공항',
};
export const LAYER_MIN_ZOOM: Record<Layer, number> = {
  fuel_station: 11,
  rest_area: 8,
  highway_incident: 7,
  airport: 5,
};
export const LAYER_PATH: Record<Layer, string> = {
  fuel_station: 'fuel-stations',
  rest_area: 'rest-areas',
  highway_incident: 'highway-incidents',
  airport: 'airports',
};

export const STATUS_RE = /\/transport\/status(\?|$)/;
export const MARKERS_RE = /\/transport\/markers-in-bounds\?/;
export const DETAIL_RE =
  /\/transport\/(fuel-stations|rest-areas|highway-incidents|airports)\/[^/?]+(\?|$)/;
export const HISTORY_RE = /\/transport\/fuel-stations\/[^/]+\/price-history/;
export const FEATURES_IN_BOUNDS_RE = /\/features\/in-bounds\?/;
/** transportFreshnessLabel(): "방금 갱신" | "n분 전 갱신" | "n시간 전 갱신" | "n일 전 갱신". */
export const FRESHNESS_RE = /(방금 갱신|\d+(분|시간|일) 전 갱신)/;
export const UNAVAILABLE_TEXT = '일시적으로 불러올 수 없음';
export const ZOOM_IN_TEXT = '확대하면 보여요';
export const LOADING_TEXT = '불러오는 중';
export const TRUNCATED_TEXT = '일부만 표시 — 확대하세요';
export const STALE_TEXT = '오래된 정보';

export const DEFAULT_EXPLORE_ZOOM = 12; // packages/domain/src/mapCenter.ts DEFAULT_MAP_ZOOM

export const controls = (page: Page): Locator => page.getByTestId('transport-layer-controls');
export const chip = (page: Page, layer: Layer): Locator =>
  page.getByTestId(`transport-layer-toggle-${layer}`);
export const stateLine = (page: Page, layer: Layer): Locator =>
  page.getByTestId(`transport-layer-state-${layer}`);
export const incidentList = (page: Page): Locator => page.getByTestId('transport-incident-list');
export const legendMarkers = (page: Page, layer?: Layer): Locator =>
  layer
    ? page.locator(`[data-testid="transport-marker"][data-layer="${layer}"]`)
    : page.getByTestId('transport-marker');
export const detailDialog = (page: Page): Locator => page.getByTestId('transport-detail');
export const detailBody = (page: Page): Locator => page.getByTestId('transport-detail-body');
export const detailError = (page: Page): Locator => page.getByTestId('transport-detail-error');
export const detailFooter = (page: Page): Locator => page.getByTestId('transport-detail-footer');
export const mapCanvas = (page: Page): Locator => page.locator('.maplibregl-canvas').first();

/** The controls only render after `/transport/status` answers `enabled=true` (prod: on). */
export async function waitForControls(page: Page): Promise<void> {
  await expect(controls(page)).toBeVisible({ timeout: 30_000 });
}

export interface MarkersQuery {
  zoom: number;
  layers: Layer[];
  bbox: [number, number, number, number];
  limit: number | null;
}

export function markersQuery(res: Response): MarkersQuery {
  const u = new URL(res.url());
  const bbox = (u.searchParams.get('bbox') ?? '').split(',').map(Number);
  return {
    zoom: Number(u.searchParams.get('zoom')),
    layers: (u.searchParams.get('layers') ?? '').split(',').filter(Boolean) as Layer[],
    bbox: [bbox[0] ?? NaN, bbox[1] ?? NaN, bbox[2] ?? NaN, bbox[3] ?? NaN],
    limit: u.searchParams.has('limit') ? Number(u.searchParams.get('limit')) : null,
  };
}

export interface LayerResult {
  layer: Layer;
  status: 'ok' | 'unavailable' | 'disabled';
  reason?: string | null;
  truncated: boolean;
  freshness?: { age_seconds: number; stale: boolean } | null;
  items: Array<{
    feature_id: string;
    coord: { lon: number; lat: number } | null;
    [k: string]: unknown;
  }>;
}

export async function markersBody(res: Response): Promise<{ zoom: number; layers: LayerResult[] }> {
  const json = (await res.json()) as { data: { zoom: number; layers: LayerResult[] } };
  return json.data;
}

/** Records every transport request URL seen on the page (never intercepts). */
export class TransportRecorder {
  readonly urls: Array<{ url: string; at: number }> = [];
  constructor(page: Page) {
    page.on('request', (req) => {
      if (/\/transport\//.test(req.url())) this.urls.push({ url: req.url(), at: Date.now() });
    });
  }
  markers(since = 0): string[] {
    return this.urls.filter((u) => u.at >= since && MARKERS_RE.test(u.url)).map((u) => u.url);
  }
  layersRequested(since = 0): Set<Layer> {
    const out = new Set<Layer>();
    for (const url of this.markers(since)) {
      for (const layer of (new URL(url).searchParams.get('layers') ?? '').split(',')) {
        if (layer) out.add(layer as Layer);
      }
    }
    return out;
  }
}

/**
 * Wait for the next markers-in-bounds response matching `pred`. The hook aborts superseded
 * requests, so we only accept responses that actually completed (status 200, never 5xx per contract).
 */
export function nextMarkersResponse(
  page: Page,
  pred: (q: MarkersQuery) => boolean = () => true,
  timeout = 30_000,
): Promise<Response> {
  return page.waitForResponse(
    (r) =>
      MARKERS_RE.test(r.url()) && r.request().method() === 'GET' && r.ok() && pred(markersQuery(r)),
    { timeout },
  );
}

/** Toggle a chip and return the markers response it triggers (the hook fetches once the map settles after the toggle, debounced; pinvi 686). */
export async function toggleExpectingRequest(
  page: Page,
  layer: Layer,
  pred: (q: MarkersQuery) => boolean = (q) => q.layers.includes(layer),
): Promise<Response> {
  const pending = nextMarkersResponse(page, pred);
  await chip(page, layer).click();
  await expect(chip(page, layer)).toHaveAttribute('aria-pressed', 'true');
  return pending;
}

/**
 * Zoom the maplibre map by whole levels with the keyboard handler ('=' / '-' = ±1 level).
 * Deterministic unlike wheel deltas, and works under the mobile project where navigation
 * controls are hidden on the trip map. The short gap lets each easeTo finish (zoomend →
 * 250 ms debounce in useTransportLayers); callers then wait on the specific request.
 */
export async function zoomBy(page: Page, steps: number): Promise<void> {
  const canvas = mapCanvas(page);
  await expect(canvas).toBeVisible();
  await canvas.focus();
  const key = steps > 0 ? '=' : '-';
  for (let i = 0; i < Math.abs(steps); i += 1) {
    await page.keyboard.press(key);
    await page.waitForTimeout(350);
  }
}

/** Pan with arrow keys (maplibre keyboard: 100 px per press) — triggers moveend → re-query. */
export async function panBy(
  page: Page,
  key: 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown',
  presses = 3,
) {
  const canvas = mapCanvas(page);
  await canvas.focus();
  for (let i = 0; i < presses; i += 1) {
    await page.keyboard.press(key);
    await page.waitForTimeout(250);
  }
}

/** 현재 검색 응답의 좌표 있는 정확 일치 결과를 선택하고 실제 카메라 완료를 기다린다. */
export async function searchAndFly(page: Page, query: string): Promise<void> {
  const result = await runSearch(page, query);
  expect(result.status).toBe(200);
  const index = coordinateFixtureIndex(result.rows, query);
  expect(index, '좌표 있는 정확 일치 검색 fixture가 있어야 한다').toBeGreaterThanOrEqual(0);
  const picked = result.rows[index]!;
  const map = await renderedMap(page);
  try {
    await searchRows(page).nth(index).click();
    await waitForCamera(map);
    await expect
      .poll(
        async () =>
          await map.evaluate((m, coord) => {
            const center = m.getCenter();
            return (
              Math.abs(m.getZoom() - 15) < 0.01 &&
              Math.abs(center.lng - coord!.lon) < 0.00001 &&
              Math.abs(center.lat - coord!.lat) < 0.00001 &&
              !m.isMoving()
            );
          }, picked.coord),
      )
      .toBe(true);
  } finally {
    await map.dispose();
  }
}

type Coord = { lon: number; lat: number };

/** 지금 캔버스 안에서 최상단으로 보이는(=사용자가 누를 수 있는) `layer` 개별 마커의 ID·이름. */
async function topmostTransportMarkers(
  page: Page,
  layer: Layer,
): Promise<Array<{ title: string; id: string }>> {
  const [items, canvasBox] = await Promise.all([
    legendMarkers(page, layer).evaluateAll((elements) =>
      elements.map((el) => ({
        title: el.textContent?.trim() ?? '',
        id: el.getAttribute('data-feature-id') ?? '',
      })),
    ),
    mapCanvas(page).boundingBox(),
  ]);
  if (!canvasBox) return [];
  const out: Array<{ title: string; id: string }> = [];
  for (const item of items) {
    const marker = page.locator(
      '.maplibregl-marker[data-interaction-id=' +
        JSON.stringify('transport:' + layer + ':' + item.id) +
        ']',
    );
    if ((await marker.count()) !== 1) continue;
    const box = await marker.boundingBox();
    if (
      !box ||
      box.x < canvasBox.x ||
      box.y < canvasBox.y ||
      box.x + box.width > canvasBox.x + canvasBox.width ||
      box.y + box.height > canvasBox.y + canvasBox.height
    )
      continue;
    const onTop = await marker.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!top && (top === el || el.contains(top));
    });
    if (onTop) out.push(item);
  }
  return out;
}

/**
 * 개별 마커가 하나도 없으면(휴게소는 상·하행 쌍이 붙어 있어 zoom 14까지 ClusterLayer 묶음이다 — #686
 * NEAR-006) 사용자가 하듯 `targets` 좌표에 가장 가까운 '묶음 펼치기'를 실제로 눌러 펼친다. 카메라가 멈추고
 * 새 viewport의 markers 응답이 온 뒤 돌아온다. 펼칠 묶음이 없으면 false.
 */
async function expandClusterToward(
  page: Page,
  layer: Layer,
  targets: readonly Coord[],
): Promise<boolean> {
  const map = await renderedMap(page);
  try {
    const pick = await map.evaluate(
      (m, coords) => {
        const rect = m.getCanvas().getBoundingClientRect();
        const projected = coords
          .map((c) => m.project([c.lon, c.lat]))
          .map((p) => ({ x: rect.left + p.x, y: rect.top + p.y }));
        let best: { index: number; distance: number } | null = null;
        // vworld-map-web ClusterMarker: 마커 루트에 aria-label "N개 위치 묶음 펼치기"(클릭 = 펼침 zoom으로 flyTo).
        const clusters = Array.from(
          document.querySelectorAll('.maplibregl-marker[aria-label*="묶음 펼치기"]'),
        );
        clusters.forEach((el, index) => {
          const r = el.getBoundingClientRect();
          const cx = r.left + r.width / 2,
            cy = r.top + r.height / 2;
          if (cx < rect.left || cx > rect.right || cy < rect.top || cy > rect.bottom) return;
          const top = document.elementFromPoint(cx, cy);
          if (!top || !(top === el || el.contains(top))) return;
          for (const p of projected) {
            const distance = Math.hypot(p.x - cx, p.y - cy);
            if (!best || distance < best.distance) best = { index, distance };
          }
        });
        if (!best) return null;
        clusters.forEach((el) => el.removeAttribute('data-e2e-expand'));
        clusters[(best as { index: number }).index]!.setAttribute('data-e2e-expand', '1');
        return true;
      },
      [...targets],
    );
    if (!pick) return false;
    const zoomBefore = await map.evaluate((m) => m.getZoom());
    const next = nextMarkersResponse(
      page,
      (q) => q.layers.includes(layer) && q.zoom > Math.floor(zoomBefore),
      45_000,
    );
    await page.locator('.maplibregl-marker[data-e2e-expand="1"]').click();
    await waitForCamera(map);
    await next;
    return true;
  } finally {
    await map.dispose();
  }
}

/**
 * Click an individually rendered transport marker of `layer` (cluster markers have other labels).
 * legend의 layer/feature ID에 해당하는 실제 마커를 정상 클릭하고 같은 ID의 상세 HTTP를 검증한다.
 * 동명 feature나 숨은 cluster를 대신 누르지 않는다. 반환값은 클릭한 이름이다.
 *
 * `expandToward`를 주면, 보이는 개별 마커가 없을 때 그 좌표 쪽 묶음을 실제 클릭으로 펼쳐(최대 4번) 다시 찾는다.
 */
export async function clickTransportMarker(
  page: Page,
  layer: Layer,
  expandToward: readonly Coord[] = [],
): Promise<string> {
  expect(
    await legendMarkers(page, layer).count(),
    'legend has requested transport markers',
  ).toBeGreaterThan(0);
  let candidates = await topmostTransportMarkers(page, layer);
  for (let round = 0; round < 4 && candidates.length === 0 && expandToward.length > 0; round += 1) {
    if (!(await expandClusterToward(page, layer, expandToward))) break;
    candidates = await topmostTransportMarkers(page, layer);
  }
  for (const item of candidates) {
    const marker = page.locator(
      '.maplibregl-marker[data-interaction-id=' +
        JSON.stringify('transport:' + layer + ':' + item.id) +
        ']',
    );
    // 동명 feature 대신 누른 transport ID의 실제 HTTP와 본문까지 연결한다.
    const response = page.waitForResponse(
      (res) =>
        res.request().method() === 'GET' &&
        new URL(res.url()).pathname.endsWith(
          '/transport/' + LAYER_PATH[layer] + '/' + encodeURIComponent(item.id),
        ),
    );
    await marker.click();
    const res = await response;
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.data.item.feature_id).toBe(item.id);
    await expect(detailDialog(page)).toBeVisible();
    await expect(detailDialog(page).locator('[data-layer]')).toHaveAttribute('data-layer', layer);
    return item.title;
  }
  throw new Error(`no individually rendered ${layer} marker could open the transport dialog`);
}

/**
 * Opens a `layer` marker near `query`. At country scale transport pins are clustered (narrow phone
 * viewports cluster every airport), so fly to the place (search → zoom 15), widen to zoom 12 — far
 * enough to include the facility, close enough that a lone airport is not clustered — and click.
 */
export async function openTransportNear(page: Page, layer: Layer, query: string): Promise<string> {
  await searchAndFly(page, query);
  // #709: 검색 결과(같은 이름의 Map 장소)를 고르면 그 장소의 선택 popup이 같은 자리에 열려(canvas 쌓임
  // 맥락 위) transport 마커를 덮는다(김포국제공항). 사용자가 하듯 popup을 닫는다.
  await dismissFeaturePopup(page);
  const pending = nextMarkersResponse(
    page,
    (q) => q.layers.includes(layer) && q.zoom <= 13,
    45_000,
  );
  await zoomBy(page, -3);
  await pending;
  return clickTransportMarker(page, layer);
}

export async function closeDetail(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect(detailDialog(page)).toHaveCount(0);
}

export type Box = { x: number; y: number; width: number; height: number };
export function boxesOverlap(a: Box, b: Box): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

/** Assert the state line of an enabled layer is one of the shapes the UI can legitimately render. */
export async function expectLayerLineShape(page: Page, layer: Layer): Promise<void> {
  const line = stateLine(page, layer);
  await expect(line).toBeVisible();
  // 켠 직후에는 "불러오는 중"이 줄을 미리 차지한다(#712) — 결과 문구로 바뀔 때까지 기다린다.
  await expect(line).not.toContainText(LOADING_TEXT, { timeout: 30_000 });
  const text = (await line.textContent()) ?? '';
  const ok = /\d+곳/.test(text) || text.includes(UNAVAILABLE_TEXT) || text.includes(ZOOM_IN_TEXT);
  expect(ok, `state line for ${layer} has a known shape: "${text}"`).toBe(true);
  if (/\d+곳/.test(text)) {
    expect(text).toContain(LAYER_LABEL[layer]);
  }
}

/** API origin as seen by the browser, derived from a real request (never hard-coded). */
export function apiOriginFrom(res: Response): string {
  const u = new URL(res.url());
  const idx = u.pathname.indexOf('/transport/');
  return `${u.origin}${u.pathname.slice(0, idx)}`;
}
