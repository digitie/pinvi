/**
 * NEAR — transport detail dialog on the explore map: fuel station (prices, history), highway
 * incident; namespace separation (ADR-076 D7); switching and closing. 휴게소·공항은 2026-11-16 지도에서
 * 뺐다(NEAR-006·NEAR-009 blocked).
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
  FRESHNESS_RE,
  HISTORY_RE,
  LAYER_PATH,
  clickTransportMarker,
  closeDetail,
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

  // NEAR-006(휴게소 상세)·NEAR-009(공항 상세)는 2026-11-16 두 레이어를 지도에서 빼며 blocked로 돌렸다.

  test('NEAR-017 transport dialog has no POI linkage (no 일정에 추가 / 상세보기 / feature link) — ADR-076 D7', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    await searchAndFly(page, '서울역'); // zoom 15 — individual (unclustered) fuel markers
    const res = await toggleExpectingRequest(page, 'fuel_station', (q) => q.zoom === 15 && q.layers.includes('fuel_station'));
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    test.skip(fuel.status !== 'ok' || fuel.items.length === 0, 'no fuel stations to open');
    await clickTransportMarker(page, 'fuel_station');
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
    await searchAndFly(page, '서울역');
    const res = await toggleExpectingRequest(page, 'fuel_station', (q) => q.zoom === 15 && q.layers.includes('fuel_station'));
    const fuel = (await markersBody(res)).layers.find((l) => l.layer === 'fuel_station')!;
    test.skip(fuel.status !== 'ok' || fuel.items.length < 2, 'need two fuel stations around 서울역');
    const first = await clickTransportMarker(page, 'fuel_station');
    await expect(detailDialog(page)).toContainText(first);
    await closeDetail(page);
    let second: string | null = null;
    try {
      second = await clickTransportMarker(page, 'fuel_station', [], [first]);
    } catch {
      second = null;
    }
    test.skip(second == null, 'data: no second individually rendered fuel station on screen');
    await expect(detailDialog(page)).toContainText(second!);
    await expect(detailDialog(page)).not.toContainText(first);
    await closeDetail(page);
    await expect(page.locator('[data-testid="transport-marker"][data-layer="fuel_station"]').first()).toBeAttached();
  });
});
