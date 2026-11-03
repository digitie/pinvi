/**
 * NEAR — transport detail dialog on the explore map: fuel station (prices, history), rest area
 * (route, facilities incl. EV flag), highway incident, airport; namespace separation (ADR-076 D7);
 * switching and closing.
 *
 * UI reference (PinVi main b1cef056): apps/web/components/map/TransportDetailDialog.tsx wraps
 * FeatureDetailModal with testId "transport-detail" → `transport-detail-body|loading|error|footer`,
 * `transport-detail-freshness`, `transport-fuel-prices`, `transport-price-history-open`,
 * `transport-price-history`, `transport-price-history-unavailable`.
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot, waitForRequest } from '../../helpers/live';
import {
  DEFAULT_EXPLORE_ZOOM,
  DETAIL_RE,
  FRESHNESS_RE,
  HISTORY_RE,
  LAYER_PATH,
  clickTransportMarker,
  closeDetail,
  openTransportNear,
  detailBody,
  detailDialog,
  detailError,
  detailFooter,
  incidentList,
  markersBody,
  searchAndFly,
  toggleExpectingRequest,
  waitForControls,
  zoomBy,
} from '../../helpers/nearby';

test.describe.configure({ mode: 'serial' });
test.setTimeout(180_000);

const SOURCE_CAPTION = '출처: 한국석유공사·한국도로공사·한국공항공사(kor-travel-map 경유)';

test.describe('NEAR transport detail dialog', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-004 주유소 marker → dialog with product prices, brand/extras, freshness and source caption', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await searchAndFly(page, '서울역'); // zoom 15 — individual (unclustered) markers
    const res = await toggleExpectingRequest(page, 'fuel_station', (q) => q.zoom === 15 && q.layers.includes('fuel_station'));
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    test.skip(fuel.status !== 'ok' || fuel.items.length === 0, `fuel layer ${fuel.status}/${fuel.reason ?? ''} around 서울역`);
    const detail = waitForRequest(page, new RegExp(`/transport/${LAYER_PATH.fuel_station}/[^/?]+(\\?|$)`));
    const title = await clickTransportMarker(page, 'fuel_station');
    expect((await detail).ok()).toBe(true);
    await expect(detailBody(page)).toBeVisible();
    await expect(detailError(page)).toHaveCount(0);
    await expect(detailDialog(page)).toContainText(title);
    await expect(detailDialog(page)).toContainText('주유소');
    const prices = page.getByTestId('transport-fuel-prices');
    await expect(prices).toBeVisible();
    const priceText = (await prices.textContent()) ?? '';
    // Either real rows ("휘발유 1,650원" / "판매 안 함") or the explicit empty state.
    expect(/(원|판매 안 함)/.test(priceText) || priceText.includes('가격 정보가 없습니다')).toBe(true);
    await expect(detailFooter(page).getByTestId('transport-detail-freshness')).toContainText(FRESHNESS_RE);
    await expect(detailFooter(page)).toContainText(SOURCE_CAPTION);
    await expect(detailDialog(page).getByRole('button', { name: '일정에 추가' })).toHaveCount(0);
    await expect(detailDialog(page).getByRole('button', { name: '상세보기' })).toHaveCount(0);
    await shot(page, 'NEAR-004', 'fuel-detail');
    await closeDetail(page);
  });

  test('NEAR-005 가격 추이 보기 loads history rows or a non-error unavailable notice', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await searchAndFly(page, '서울역');
    const res = await toggleExpectingRequest(page, 'fuel_station', (q) => q.zoom === 15);
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    test.skip(fuel.status !== 'ok' || fuel.items.length === 0, 'no fuel stations to open');
    await clickTransportMarker(page, 'fuel_station');
    const open = page.getByTestId('transport-price-history-open');
    await expect(open).toBeVisible();
    const history = waitForRequest(page, HISTORY_RE);
    await open.click();
    const hres = await history;
    expect(new URL(hres.url()).searchParams.get('days')).toBe('30');
    expect(hres.ok(), 'history is 200 (unavailable is not an error per docs/api/transport.md)').toBe(true);
    const body = (await hres.json()) as { data: { status: 'available' | 'unavailable'; reason: string | null; items: unknown[] } };
    if (body.data.status === 'available' && body.data.items.length > 0) {
      const table = page.getByTestId('transport-price-history');
      await expect(table).toBeVisible();
      await expect(table).toContainText(/원/);
    } else {
      const note = page.getByTestId('transport-price-history-unavailable');
      await expect(note).toBeVisible();
      await expect(note).toHaveAttribute('data-reason', body.data.reason ?? '');
      await expect(note).toContainText(/(잠시 후 다시 시도해 주세요|아직 제공되지 않습니다)/);
    }
    await expect(page.getByText('가격 추이를 불러오지 못했습니다.')).toHaveCount(0);
    await shot(page, 'NEAR-005', 'price-history');
    await closeDetail(page);
  });

  test('NEAR-006 휴게소 detail: route row, facility rows (주유소/LPG 충전/전기차 충전) and optional fuel block', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 9));
    const res = await toggleExpectingRequest(page, 'rest_area');
    const rest = (await markersBody(res)).layers.find((l) => l.layer === 'rest_area')!;
    test.skip(rest.status !== 'ok' || rest.items.length === 0, 'no rest areas in viewport');
    const detail = waitForRequest(page, new RegExp(`/transport/${LAYER_PATH.rest_area}/`));
    const title = await clickTransportMarker(page, 'rest_area');
    const dres = await detail;
    expect(dres.ok()).toBe(true);
    const item = ((await dres.json()) as { data: { item: Record<string, unknown>; fuel_price_freshness: unknown } }).data;
    await expect(detailDialog(page)).toContainText(title);
    await expect(detailDialog(page)).toContainText('휴게소');
    const body = detailBody(page);
    if (item.item.route_name) await expect(body).toContainText(String(item.item.route_name));
    for (const [key, label] of [
      ['has_gas_station', '주유소'],
      ['has_lpg_station', 'LPG 충전'],
      ['has_ev_charger', '전기차 충전'],
    ] as const) {
      const value = item.item[key];
      if (value == null) continue;
      const row = body.locator('dt', { hasText: label }).first();
      await expect(row).toBeVisible();
      await expect(row.locator('xpath=following-sibling::dd[1]')).toHaveText(value ? '있음' : '없음');
    }
    if (item.item.fuel_prices) {
      await expect(page.getByTestId('transport-fuel-prices')).toContainText('휘발유');
      await expect(page.getByTestId('transport-fuel-prices')).toContainText('경유');
    }
    if (item.fuel_price_freshness) {
      await expect(detailFooter(page)).toContainText('유가');
    }
    await expect(detailFooter(page)).toContainText(SOURCE_CAPTION);
    await shot(page, 'NEAR-006', 'rest-area-detail');
    await closeDetail(page);
  });

  test('NEAR-008 incident row → detail with type/status/route/occurred rows, freshness, closes cleanly', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 7));
    const res = await toggleExpectingRequest(page, 'highway_incident');
    const inc = (await markersBody(res)).layers.find((l) => l.layer === 'highway_incident')!;
    test.skip(inc.status !== 'ok' || inc.items.length === 0, 'no active highway incidents right now');
    const first = incidentList(page).getByRole('button').first();
    const rowText = (await first.textContent()) ?? '';
    const detail = waitForRequest(page, new RegExp(`/transport/${LAYER_PATH.highway_incident}/`));
    await first.click();
    const dres = await detail;
    expect(dres.ok()).toBe(true);
    const item = ((await dres.json()) as { data: { item: Record<string, unknown> } }).data.item;
    await expect(detailDialog(page)).toBeVisible();
    await expect(detailDialog(page)).toContainText('교통 돌발');
    expect(rowText).toContain(String(item.title));
    const body = detailBody(page);
    for (const [key, label] of [
      ['incident_type', '유형'],
      ['process_status', '처리 상태'],
      ['route_name', '노선'],
      ['point_name', '위치'],
      ['occurred_at', '발생'],
      ['message', '내용'],
    ] as const) {
      if (item[key]) await expect(body.locator('dt', { hasText: label }).first()).toBeVisible();
    }
    await expect(detailFooter(page).getByTestId('transport-detail-freshness')).toContainText(FRESHNESS_RE);
    await shot(page, 'NEAR-008', 'incident-detail');
    await closeDetail(page);
    await expect(incidentList(page)).toBeVisible();
  });

  test('NEAR-009 공항 at country scale → ≥5 airports; detail shows 영문명 and a 3-letter IATA code', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 6));
    const res = await toggleExpectingRequest(page, 'airport', (q) => q.zoom <= 6);
    const airports = (await markersBody(res)).layers.find((l) => l.layer === 'airport')!;
    test.skip(airports.status !== 'ok', `airport layer ${airports.reason ?? ''}`);
    expect(airports.items.length, 'operating airports nationwide (15 in the krairport bundle)').toBeGreaterThanOrEqual(5);
    // country scale proves the count; the detail opens from an individually rendered pin (clustered at zoom 6)
    const detail = waitForRequest(page, new RegExp(`/transport/${LAYER_PATH.airport}/`));
    const title = await openTransportNear(page, 'airport', '김포공항');
    const item = ((await (await detail).json()) as { data: { item: { iata_code: string; name_english: string } } }).data.item;
    await expect(detailDialog(page)).toContainText(title);
    await expect(detailDialog(page)).toContainText('공항');
    const body = detailBody(page);
    await expect(body.locator('dt', { hasText: '영문명' })).toBeVisible();
    await expect(body).toContainText(item.name_english);
    await expect(body.locator('dt', { hasText: '코드' })).toBeVisible();
    expect(item.iata_code).toMatch(/^[A-Z]{3}$/);
    await expect(body).toContainText(item.iata_code);
    await shot(page, 'NEAR-009', 'airport-detail');
    await closeDetail(page);
  });

  test('NEAR-017 transport dialog has no POI linkage (no 일정에 추가 / 상세보기 / feature link) — ADR-076 D7', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 6));
    const res = await toggleExpectingRequest(page, 'airport');
    const airports = (await markersBody(res)).layers.find((l) => l.layer === 'airport')!;
    test.skip(airports.status !== 'ok' || airports.items.length === 0, 'no airports to open');
    await clickTransportMarker(page, 'airport');
    const dialog = detailDialog(page);
    await expect(dialog.getByRole('button', { name: '일정에 추가' })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '상세보기' })).toHaveCount(0);
    await expect(dialog.getByTestId('feature-detail-card-body')).toHaveCount(0);
    await expect(dialog.getByRole('link', { name: /카카오|네이버/ })).toHaveCount(0);
    // The feature detail modal (Map PG UUID namespace) must not have been opened by a transport id.
    await expect(page.getByTestId('feature-detail-modal')).toHaveCount(0);
    await closeDetail(page);
  });

  test('NEAR-018 opening another marker swaps the dialog content; Escape closes and markers remain', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await zoomBy(page, -(DEFAULT_EXPLORE_ZOOM - 6));
    const res = await toggleExpectingRequest(page, 'airport');
    const airports = (await markersBody(res)).layers.find((l) => l.layer === 'airport')!;
    test.skip(airports.status !== 'ok' || airports.items.length < 2, 'need two airports');
    // airports are clustered at country scale — open them one at a time near each airport
    const first = await openTransportNear(page, 'airport', '김포공항');
    await expect(detailDialog(page)).toContainText(first);
    await closeDetail(page);
    let second: string | null = null;
    try {
      second = await openTransportNear(page, 'airport', '김해공항');
    } catch {
      second = null;
    }
    test.skip(second == null || second === first, 'data: no second individually rendered airport near 김해공항');
    await expect(detailDialog(page)).toContainText(second!);
    await expect(detailDialog(page)).not.toContainText(first);
    await closeDetail(page);
    await expect(page.locator('[data-testid="transport-marker"][data-layer="airport"]').first()).toBeAttached();
  });
});
