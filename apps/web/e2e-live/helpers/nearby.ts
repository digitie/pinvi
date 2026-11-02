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
  items: Array<{ feature_id: string; coord: { lon: number; lat: number } | null; [k: string]: unknown }>;
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
    (r) => MARKERS_RE.test(r.url()) && r.request().method() === 'GET' && r.ok() && pred(markersQuery(r)),
    { timeout },
  );
}

/** Toggle a chip and return the markers response it triggers (the hook fetches immediately on toggle). */
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
export async function panBy(page: Page, key: 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown', presses = 3) {
  const canvas = mapCanvas(page);
  await canvas.focus();
  for (let i = 0; i < presses; i += 1) {
    await page.keyboard.press(key);
    await page.waitForTimeout(250);
  }
}

/** Explore map search → pick first result → map flies to it at zoom 15 (FeatureMapView.handleSearchSelect). */
export async function searchAndFly(page: Page, query: string): Promise<void> {
  const search = page.getByTestId('map-search').first();
  const input = search.getByRole('textbox', { name: '장소·주소 검색' });
  await input.fill(query);
  const first = search.locator('li button').first();
  await expect(first).toBeVisible({ timeout: 20_000 });
  await first.click();
}

/**
 * Click an individually rendered transport marker of `layer` (cluster markers have other labels).
 * Tries legend titles in order until a `.maplibregl-marker[aria-label=title]` inside the canvas box
 * opens the transport dialog. Returns the title clicked.
 */
export async function clickTransportMarker(page: Page, layer: Layer): Promise<string> {
  const titles = await legendMarkers(page, layer).allTextContents();
  expect(titles.length, `legend has ${layer} markers`).toBeGreaterThan(0);
  const canvasBox = await mapCanvas(page).boundingBox();
  expect(canvasBox).not.toBeNull();
  for (const title of titles) {
    const marker = page.locator('.maplibregl-marker').and(page.getByLabel(title, { exact: true })).first();
    if ((await marker.count()) === 0) continue;
    const box = await marker.boundingBox();
    if (!box || !canvasBox) continue;
    const inside =
      box.x >= canvasBox.x && box.y >= canvasBox.y &&
      box.x + box.width <= canvasBox.x + canvasBox.width &&
      box.y + box.height <= canvasBox.y + canvasBox.height;
    if (!inside) continue;
    await marker.click({ force: true });
    try {
      await expect(detailDialog(page)).toBeVisible({ timeout: 5_000 });
      return title;
    } catch {
      // A same-named Map feature marker may have taken the click; close whatever opened and try the next.
      await page.keyboard.press('Escape');
    }
  }
  throw new Error(`no individually rendered ${layer} marker could open the transport dialog`);
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
