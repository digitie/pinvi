/**
 * POI area — search paths that end in a my-POI, my-POI vs feature distinctions, duplicates.
 * Cases: POI-007, 008, 009, 016, 017, 018, 019. Desktop only (search overlay is the same on
 * mobile but the panel toggling adds no coverage).
 */
import { expect, test, type Page } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, waitForMapIdle } from '../../helpers/live';
import {
  createManualPoi,
  dayBadge,
  deleteAllPoisInDay,
  e2eName,
  gotoTrip,
  manualDialog,
  mapSearchContainer,
  mapSearchInput,
  mapStats,
  markerLegend,
  pickSearchRow,
  poiList,
  rightClickMap,
  searchPlaces,
  selectDay,
  snap,
  submitManualDialog,
} from '../../helpers/poi';

let tripId: string | null = null;
let dayCount = 1;

async function freshTrip(page: Page, label: string, days = 1): Promise<string> {
  await loginAsUser(page);
  dayCount = days;
  const trip = await createTrip(page, {
    title: e2eName(label),
    start: '2026-11-05',
    end: days === 1 ? '2026-11-05' : '2026-11-06',
  });
  tripId = trip.id;
  await gotoTrip(page, trip.id);
  await selectDay(page, 1);
  return trip.id;
}

test.skip(({ isMobile }) => isMobile, 'desktop-only cases');

test.afterEach(async ({ page }) => {
  if (!tripId) return;
  const id = tripId;
  tripId = null;
  try {
    await gotoTrip(page, id);
    for (let d = 1; d <= dayCount; d += 1) {
      await selectDay(page, d);
      await deleteAllPoisInDay(page);
    }
  } catch {
    // fall through to trip deletion
  }
  await deleteTrip(page, id);
});

test('POI-007 검색 결과 없음 → 우클릭 생성', async ({ page }) => {
  const id = await freshTrip(page, 'POI 검색없음');
  await searchPlaces(page, '[e2e]zq없는장소x9');
  const alert = mapSearchContainer(page).getByRole('alert');
  await expect(alert).toHaveText('검색 결과가 없습니다.', { timeout: 20_000 });
  await expect(mapSearchContainer(page).locator('[data-testid^="map-search-result-"]')).toHaveCount(0);
  // no "add anyway" affordance exists in the search UI — the map is the only path
  await expect(mapSearchContainer(page).getByRole('button')).toHaveCount(0);
  await snap(page, 'POI-007', 'no-result');

  await rightClickMap(page);
  await expect(manualDialog(page)).toBeVisible();
  const name = e2eName('없던 곳');
  await submitManualDialog(page, id, name);
  await expect(markerLegend(page).filter({ hasText: name })).toHaveCount(1);
  await expect(dayBadge(page, 1)).toHaveText('1곳');
});

test('POI-008 주소 검색 결과 pick → manual POI', async ({ page }) => {
  const id = await freshTrip(page, 'POI 주소검색');
  await searchPlaces(page, '세종대로 110');
  const addressRows = mapSearchContainer(page).getByTestId('map-search-result-address');
  test.skip((await addressRows.count()) === 0, 'geo 주소 검색이 이 질의에 주소 행을 주지 않음(데이터 의존)');
  await snap(page, 'POI-008', 'results');
  const { rowText, body } = await pickSearchRow(page, id, 'address');
  expect(body.source).toBe('manual');
  expect(body.feature_id).toBeNull();
  expect(body.external_ref).toBeNull();
  const snapshot = body.feature_snapshot as { name: string };
  expect(rowText).toContain(snapshot.name);
  const row = poiList(page).getByRole('listitem').filter({ hasText: snapshot.name });
  await expect(row).toHaveCount(1);
  await expect(markerLegend(page).filter({ hasText: snapshot.name })).toHaveAttribute(
    'data-feature-resolution-state',
    'not_linked',
  );
});

test('POI-009 my-POI vs Map feature — 범례 속성 비교 (map:heritage 안동하회마을)', async ({ page }) => {
  const id = await freshTrip(page, 'POI 비교');
  await searchPlaces(page, '안동하회마을');
  const { body: featureBody } = await pickSearchRow(page, id, 'feature', /하회/);
  expect(featureBody.source).toBe('feature');
  expect(typeof featureBody.feature_id).toBe('string');
  const featureName = (featureBody.feature_snapshot as { name: string }).name;
  await waitForMapIdle(page);

  const manualName = e2eName('수동 비교');
  await createManualPoi(page, id, manualName, { dx: 140, dy: 60 });

  const featureLegend = markerLegend(page).filter({ hasText: featureName });
  const manualLegend = markerLegend(page).filter({ hasText: manualName });
  await expect(featureLegend).toHaveCount(1);
  await expect(manualLegend).toHaveCount(1);
  await expect(featureLegend).toHaveAttribute('data-feature-resolution-state', /^(found|unverified)$/);
  await expect(featureLegend).not.toHaveAttribute('data-marker-category', '');
  await expect(manualLegend).toHaveAttribute('data-feature-resolution-state', 'not_linked');
  await expect(manualLegend).toHaveAttribute('data-marker-color', 'P-08');
  await expect(manualLegend).toHaveAttribute('data-marker-icon', 'marker');
  await expect(manualLegend).toHaveAttribute('data-marker-category', '');
  // manual rows carry no resolution icon (not_linked → featureResolutionNotice null)
  const manualRow = poiList(page).getByRole('listitem').filter({ hasText: manualName });
  await expect(manualRow.locator('svg[aria-label]')).toHaveCount(0);
  await expect(mapStats(page)).toContainText('장소 2곳');
  await snap(page, 'POI-009', 'compare');
});

test('POI-016 feature 상세 "카카오·네이버에서 더 보기"는 POI 를 만들지 않는다 (map:heritage 불국사)', async ({ page }) => {
  const id = await freshTrip(page, 'POI enrichment');
  await searchPlaces(page, '불국사');
  await pickSearchRow(page, id, 'feature', /불국사/);
  await waitForMapIdle(page);
  await expect(dayBadge(page, 1)).toHaveText('1곳');

  const featureMarkers = page.locator('.trip-map-feature-marker');
  // Nearby features load after the trip view (separate in-bounds fetch) — wait before deciding.
  await expect.poll(() => featureMarkers.count(), { timeout: 20_000 }).toBeGreaterThan(0).catch(() => undefined);
  test.skip((await featureMarkers.count()) === 0, '뷰포트에 feature 마커 없음(데이터 의존)');
  let posted = 0;
  page.on('request', (r) => {
    if (r.method() === 'POST' && new URL(r.url()).pathname === `/trips/${id}/pois`) posted += 1;
  });
  await featureMarkers.first().click();
  await page.getByTestId('trip-map-detail-open').click();
  const more = page.getByRole('button', { name: '카카오·네이버에서 더 보기' });
  await expect(more).toBeVisible({ timeout: 20_000 });
  await more.click();
  await expect(
    page.getByText('외부 정보 불러오는 중…').or(page.getByText('일부 외부 정보를 불러오지 못했습니다.')).or(
      page.getByText(/카카오|네이버 검색/).last(),
    ),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText('외부 정보 불러오는 중…')).toHaveCount(0, { timeout: 30_000 });
  await snap(page, 'POI-016', 'enrichment');
  await page.keyboard.press('Escape');
  expect(posted).toBe(0);
  await expect(dayBadge(page, 1)).toHaveText('1곳');
});

test('POI-017 같은 Map 장소를 같은 일자에 두 번 추가 (map:heritage 안동하회마을)', async ({ page }) => {
  const id = await freshTrip(page, 'POI 중복');
  await searchPlaces(page, '안동하회마을');
  const first = await pickSearchRow(page, id, 'feature', /하회/);
  // Like a user, wait for the list to show the first add before picking again — the web appends after
  // the last sort_order it knows, so a second pick against a stale view is a 409 SORT_ORDER_CONFLICT.
  await expect(poiList(page).getByRole('listitem')).toHaveCount(1, { timeout: 20_000 });
  await searchPlaces(page, '안동하회마을');
  const second = await pickSearchRow(page, id, 'feature', /하회/);
  expect(second.body.feature_id).toBe(first.body.feature_id);
  const name = (first.body.feature_snapshot as { name: string }).name;
  await expect(poiList(page).getByRole('listitem').filter({ hasText: name })).toHaveCount(2);
  await expect(dayBadge(page, 1)).toHaveText('2곳');
  await expect(mapStats(page)).toContainText('장소 2곳');
  await snap(page, 'POI-017', 'duplicate');
});

test('POI-018 같은 장소를 1일차·2일차에 추가 (map:tourist 고씨굴)', async ({ page }) => {
  const id = await freshTrip(page, 'POI 두일자', 2);
  await searchPlaces(page, '고씨굴');
  await pickSearchRow(page, id, 'feature', /고씨/);
  await expect(dayBadge(page, 1)).toHaveText('1곳');
  await selectDay(page, 2);
  await searchPlaces(page, '고씨굴');
  const second = await pickSearchRow(page, id, 'feature', /고씨/);
  expect(second.body.day_index).toBe(2);
  await expect(dayBadge(page, 2)).toHaveText('1곳');
  await expect(dayBadge(page, 1)).toHaveText('1곳');
  await expect(mapStats(page)).toContainText('2일 표시');
  await expect(mapStats(page)).toContainText('장소 2곳');
  await snap(page, 'POI-018', 'two-days');
});

test('POI-019 내 my-POI 가 통합 검색에 "내 여행" 배지로 나온다', async ({ page }) => {
  const id = await freshTrip(page, 'POI 내검색');
  const name = e2eName('내장소');
  await createManualPoi(page, id, name);
  await searchPlaces(page, name);
  const mine = mapSearchContainer(page).getByTestId('map-search-result-my_poi').filter({ hasText: name });
  await expect(mine.first()).toBeVisible({ timeout: 20_000 });
  await expect(mine.first()).toContainText('내 여행');
  await snap(page, 'POI-019', 'my-poi-row');
  const { body } = await pickSearchRow(page, id, 'my_poi', new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  expect(body.source).toBe('manual');
  await expect(dayBadge(page, 1)).toHaveText('2곳');
  await expect(mapSearchInput(page)).toHaveValue('');
});
