/**
 * WX — sunrise/sunset (KASI day rise/set) in trip detail.
 * Cases: WX-010 (fresh trip pending states, desktop+mobile), WX-011 (seed trip vs NOAA ±5 min), WX-012 (reference label).
 * Facts (PinVi main 620b6046):
 *  - apps/api/app/services/trip_day_rise_set.py — status pending_date/pending_coord/pending_fetch; coords = centroid of the day's POIs;
 *    reference = created_at-earliest POI name.
 *  - apps/etl/pinvi/etl/schedules.py — pinvi_trip_day_rise_sets_schedule cron "*\/20 * * * *" (fills pending_fetch/stale).
 *  - apps/web/components/trips/TripDayHeader.tsx — testids trip-day-rise-set / trip-day-rise-set-pending[data-rise-set-status], #615 wording.
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import { NOAA_SELF_CHECK, clockDiffMin, hhmmToMin, noaaSunTimesKst } from '../../helpers/sun';
import {
  D,
  SEED_SUN_TRIP_TITLE,
  TEXT,
  annotate,
  centroid,
  dayOf,
  loadTripView,
  onMobile,
  openDay,
  parseRiseSet,
  poiCoord,
  poiName,
  reloadTripView,
  risePending,
  riseSuccess,
  useTripCleanup,
  wxTitle,
  type WxDay,
  type WxTripView,
} from '../../helpers/weather';

const SUN_TOLERANCE_MIN = 5;

async function expectNoaaMatch(day: WxDay, uiText: string): Promise<void> {
  const coords = day.pois.map(poiCoord).filter((c): c is { lon: number; lat: number } => c != null);
  expect(coords.length, `${day.day_index}일차 POI 좌표`).toBeGreaterThan(0);
  const c = centroid(coords);
  const date = day.effective_date ?? day.date;
  expect(date).toBeTruthy();
  const noaa = noaaSunTimesKst(c.lat, c.lon, date!);
  expect(noaa).not.toBeNull();
  const ui = parseRiseSet(uiText);
  expect(ui.sunrise, 'UI 일출').toBeTruthy();
  expect(ui.sunset, 'UI 일몰').toBeTruthy();
  const dRise = clockDiffMin(hhmmToMin(ui.sunrise!)!, noaa!.sunriseMin);
  const dSet = clockDiffMin(hhmmToMin(ui.sunset!)!, noaa!.sunsetMin);
  annotate(`${day.day_index}일차 ${date} @(${c.lat.toFixed(3)},${c.lon.toFixed(3)}) UI ${ui.sunrise}/${ui.sunset} NOAA ${noaa!.sunrise}/${noaa!.sunset} Δ ${dRise}/${dSet}min`);
  expect(dRise, '일출 NOAA ±5분').toBeLessThanOrEqual(SUN_TOLERANCE_MIN);
  expect(dSet, '일몰 NOAA ±5분').toBeLessThanOrEqual(SUN_TOLERANCE_MIN);
}

/** Open the trip list and click the seed trip by title. Declared as "helper needed" (openTripByTitle) in README. */
async function openSeedTrip(page: import('@playwright/test').Page): Promise<string | null> {
  for (const path of ['/trips', '/']) {
    await page.goto(path);
    const list = page.getByTestId('trip-list');
    if (!(await list.isVisible({ timeout: 8_000 }).catch(() => false))) continue;
    const link = list.getByRole('link').filter({ hasText: SEED_SUN_TRIP_TITLE }).first();
    if (!(await link.isVisible({ timeout: 3_000 }).catch(() => false))) return null;
    const href = await link.getAttribute('href');
    const m = href?.match(/\/trips\/([0-9a-f-]{36})/i);
    return m?.[1] ?? null;
  }
  return null;
}

test.describe('weather · sunrise/sunset', () => {
  test.setTimeout(180_000);
  const trips = useTripCleanup();

  test('NOAA helper self-check (2026-11-02 e2e 관측값)', async () => {
    const s = noaaSunTimesKst(NOAA_SELF_CHECK.lat, NOAA_SELF_CHECK.lon, NOAA_SELF_CHECK.date)!;
    expect(clockDiffMin(s.sunriseMin, hhmmToMin(NOAA_SELF_CHECK.sunrise)!)).toBeLessThanOrEqual(NOAA_SELF_CHECK.toleranceMin);
    expect(clockDiffMin(s.sunsetMin, hhmmToMin(NOAA_SELF_CHECK.sunset)!)).toBeLessThanOrEqual(NOAA_SELF_CHECK.toleranceMin);
  });

  test.describe('WX-010 (desktop + mobile)', () => {
    test('WX-010 빈 일자 pending_coord → 장소 추가 후 pending_fetch', async ({ page }) => {
      await loginAsUser(page);
      const { id } = await createTrip(page, { title: wxTitle('WX-010'), start: D(1), end: D(2) });
      trips.track(id);
      await loadTripView(page, id);
      let article = await openDay(page, 1);
      let pending = risePending(article);
      await expect(pending).toBeVisible();
      await expect(pending).toHaveAttribute('data-rise-set-status', 'pending_coord');
      await expect(pending).toHaveText(TEXT.risePending.pending_coord);
      await expect(article.getByTestId('trip-day-rise-set')).toHaveCount(0);
      await shot(page, 'WX-010', 'pending-coord');

      await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
      const view = await reloadTripView(page, id);
      const day1 = dayOf(view, 1);
      article = await openDay(page, 1);
      const status = day1.rise_set?.status;
      annotate(`after add: rise_set.status=${status}`);
      if (status === 'success') {
        // ETL ran between add and reload (20-min cycle) — verify the values instead.
        const ok = riseSuccess(article);
        await expect(ok).toBeVisible();
        await expectNoaaMatch(day1, await ok.innerText());
      } else {
        expect(status).toBe('pending_fetch');
        pending = risePending(article);
        await expect(pending).toHaveAttribute('data-rise-set-status', 'pending_fetch');
        await expect(pending).toHaveText(TEXT.risePending.pending_fetch);
      }
      await shot(page, 'WX-010', 'pending-fetch');

      const article2 = await openDay(page, 2);
      const pending2 = risePending(article2);
      await expect(pending2).toHaveAttribute('data-rise-set-status', 'pending_coord');
      await expect(pending2).toHaveText(TEXT.risePending.pending_coord);
    });
  });

  test.describe('seed trip (read-only)', () => {
    test.skip(onMobile, '데스크톱 전용');
    let view: WxTripView | null = null;
    let seedId: string | null = null;

    test.beforeEach(async ({ page }) => {
      await loginAsUser(page);
      seedId = await openSeedTrip(page);
      test.skip(seedId == null, `시드 여행 '${SEED_SUN_TRIP_TITLE}' 이 없다 — README §Preconditions 대로 미리 만들 것`);
      view = await loadTripView(page, seedId!);
    });

    test('WX-011 일출·일몰이 NOAA 와 ±5분 (영월·제주·설악산·서울·울릉도)', async ({ page }) => {
      const successDays = view!.days.filter((d) => d.rise_set?.status === 'success' && d.pois.length > 0);
      const pendingDays = view!.days.filter((d) => d.rise_set?.status?.startsWith('pending'));
      annotate(`days=${view!.days.length} success=${successDays.length} pending=${pendingDays.length}`);
      expect(successDays.length, '시드 여행에 success 일자가 없다(ETL 미실행 또는 시드 낡음)').toBeGreaterThan(0);
      for (const day of successDays) {
        const article = await openDay(page, day.day_index);
        const ok = riseSuccess(article);
        await expect(ok).toBeVisible();
        await expectNoaaMatch(day, await ok.innerText());
        await shot(page, 'WX-011', `day${day.day_index}`);
      }
      expect.soft(pendingDays.length, '시드 일자 중 pending 이 남아 있으면 ETL 지연').toBe(0);
    });

    test('WX-012 "기준" 라벨은 가장 먼저 추가된 장소 이름', async ({ page }) => {
      const day = view!.days.find((d) => d.rise_set?.status === 'success' && d.pois.length > 0);
      test.skip(day == null, 'success 일자 없음(WX-011 참고)');
      const first = [...day!.pois].sort((a, b) => a.created_at.localeCompare(b.created_at))[0]!;
      expect(day!.rise_set_reference, 'rise_set_reference == 첫 POI 이름').toBe(poiName(first));
      const article = await openDay(page, day!.day_index);
      await expect(riseSuccess(article)).toContainText(`${day!.rise_set_reference} 기준`);
    });
  });
});
