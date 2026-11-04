/**
 * SRCH-013..018 — region bias (#615) and search-to-add inside a trip. MUTATING: every test creates its own
 * `[e2e]` trip and deletes it in afterEach (also on failure).
 * Contract: GET /search?bbox=lng_min,lat_min,lng_max,lat_max — order-only bias; trip bbox = POI extent ± 0.25°,
 * cap limit//2 (=4) regional rows at the front, rest keep Map order (apps/api/app/services/place_search.py
 * region_biased_items; apps/web/lib/searchBias.ts).
 */
import { expect, test, type Page } from '@playwright/test';
import { createTrip, deleteTrip, e2ePrefix, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import { desktopOnly, featureRows, insideBbox, runSearch, searchRows } from '../../helpers/search';

const START = '2026-11-20';
const END = '2026-11-22';
const HAHOE = { lon: 128.52, lat: 36.54 }; // 안동하회마을 approx — only used to sanity-check the bbox

async function openDay1(page: Page, tripId: string) {
  await page.goto(`/trips/${tripId}`);
  await page.getByRole('tab', { name: '1일차' }).click();
  await expect(page.getByTestId('trip-map-place-search').getByTestId('map-search')).toBeVisible({ timeout: 15_000 });
}

test.describe('SRCH region bias + add from search (trip, mutating)', () => {
  desktopOnly();
  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    while (created.length) {
      const id = created.pop()!;
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  async function tripWithHahoe(page: Page, id: string): Promise<string> {
    const trip = await createTrip(page, { title: `${e2ePrefix} ${id}`, start: START, end: END, region: '경북 안동시' });
    created.push(trip.id);
    await page.goto(`/trips/${trip.id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (row) => row.includes('하회마을') && row.includes('장소'));
    await openDay1(page, trip.id);
    return trip.id;
  }

  test('SRCH-013 여행 범위 안 결과가 먼저', async ({ page }) => {
    await tripWithHahoe(page, 'SRCH-013');
    const scope = page.getByTestId('trip-map-place-search');
    const out = await runSearch(page, '카페', { scope });
    expect(out.bbox, 'bias bbox sent').not.toBeNull();
    const bbox = out.bbox!;
    expect(HAHOE.lon).toBeGreaterThanOrEqual(bbox[0]);
    expect(HAHOE.lon).toBeLessThanOrEqual(bbox[2]);
    expect(HAHOE.lat).toBeGreaterThanOrEqual(bbox[1]);
    expect(HAHOE.lat).toBeLessThanOrEqual(bbox[3]);
    const feats = featureRows(out.rows);
    const insideCount = feats.filter((r) => insideBbox(r, bbox)).length;
    const lead = Math.min(4, insideCount);
    for (let i = 0; i < lead; i += 1) {
      expect.soft(insideBbox(feats[i]!, bbox), `feature row ${i} (${feats[i]!.name}) inside trip bbox`).toBe(true);
    }
    await shot(page, 'SRCH-013', 'biased-results');
  });

  test('SRCH-014 지역 밖 정확 일치는 살아남는다', async ({ page }) => {
    await tripWithHahoe(page, 'SRCH-014');
    const scope = page.getByTestId('trip-map-place-search');
    const out = await runSearch(page, '성산일출봉', { scope });
    const hit = featureRows(out.rows).find((r) => r.name.replace(/\s/g, '').includes('성산일출봉'));
    expect(hit, '성산일출봉 feature row present').toBeTruthy();
    if (out.bbox && hit) expect(insideBbox(hit, out.bbox), 'result is outside the trip bbox').toBe(false);
    await expect(searchRows(page, 'feature', scope).filter({ hasText: '성산일출봉' }).first()).toBeVisible();
  });

  test('SRCH-015 지역 안 결과는 최대 limit//2', async ({ page }, testInfo) => {
    await tripWithHahoe(page, 'SRCH-015');
    const scope = page.getByTestId('trip-map-place-search');
    const out = await runSearch(page, '찜닭', { scope });
    expect(out.bbox).not.toBeNull();
    const bbox = out.bbox!;
    const feats = featureRows(out.rows);
    const insideCount = feats.filter((r) => insideBbox(r, bbox)).length;
    let leadingInside = 0;
    for (const r of feats) {
      if (insideBbox(r, bbox)) leadingInside += 1;
      else break;
    }
    testInfo.annotations.push({ type: 'data', description: `feature rows=${feats.length} inside=${insideCount} leadingInside=${leadingInside}` });
    expect.soft(leadingInside).toBeGreaterThanOrEqual(Math.min(4, insideCount));
    const outside = feats.filter((r) => !insideBbox(r, bbox));
    for (const r of outside) {
      await expect(searchRows(page, 'feature', scope).filter({ hasText: r.name }).first()).toBeVisible();
    }
  });

  test('SRCH-017 검색 결과를 일자에 추가', async ({ page }) => {
    const trip = await createTrip(page, { title: `${e2ePrefix} SRCH-017`, start: START, end: END });
    created.push(trip.id);
    await page.goto(`/trips/${trip.id}`);
    const name = await searchAndAddPlace(page, 1, '소수서원', (row) => row.includes('소수서원') && row.includes('장소'));
    expect(name).toContain('소수서원');
    await page.goto(`/trips/${trip.id}`);
    await expect(page.getByTestId('trip-poi-list').locator('li').filter({ hasText: '소수서원' }).first()).toBeVisible({ timeout: 15_000 });
    await expect.soft(page.getByRole('region', { name: '여행 지도' }).getByText('장소 1곳', { exact: true })).toBeVisible();
    await shot(page, 'SRCH-017', 'poi-added');
  });

  test('SRCH-018 내 여행 POI가 내 여행 배지로 검색된다', async ({ page }) => {
    const title = `${e2ePrefix} SRCH-018`;
    const trip = await createTrip(page, { title, start: START, end: END });
    created.push(trip.id);
    await page.goto(`/trips/${trip.id}`);
    await searchAndAddPlace(page, 1, '도산서원', (row) => row.includes('도산서원') && row.includes('장소'));
    await page.goto('/map');
    const out = await runSearch(page, '도산서원');
    const mine = out.rows.filter((r) => r.source === 'my_poi' && r.trip_title === title);
    expect(mine.length, 'my_poi row for this trip').toBeGreaterThan(0);
    await expect(searchRows(page, 'my_poi').filter({ hasText: '도산서원' }).first()).toContainText('내 여행');
    await shot(page, 'SRCH-018', 'my-poi-row');
  });
});
