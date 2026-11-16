/**
 * WX — 일출·일몰 즉시 계산(astral, 2026-11-16 소유자 요청 18)과 일자 요일·공휴일(요청 17).
 * Cases: WX-040 (장소 추가 직후 일자·장소 일출·일몰), TRIP-071 (요일·공휴일 강조).
 * Facts:
 *  - apps/api/app/services/sun_times.py — astral 계산, 분 반올림, status success|pending_date|pending_coord|failed.
 *  - apps/api/app/services/trip_view_builder.py — day rise_set = 일자 POI centroid, poi rise_set = POI 좌표.
 *  - apps/web/components/trips/TripDayHeader.tsx — trip-day-date[data-day-tone], trip-day-weekday, trip-poi-rise-set.
 *  - 공휴일 이름은 PinVi ETL kasi_special_days_job(KASI 특일, is_holiday)이 채운 행이다.
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import { clockDiffMin, hhmmToMin, noaaSunTimesKst } from '../../helpers/sun';
import {
  annotate,
  dayOf,
  loadTripView,
  onMobile,
  openDay,
  parseRiseSet,
  poiCoord,
  poiRow,
  reloadTripView,
  riseSuccess,
  useTripCleanup,
  wxTitle,
  D,
} from '../../helpers/weather';

test.describe('일출·일몰 즉시 계산 · 요일', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용');
  const trips = useTripCleanup();

  test('WX-040 장소를 추가하면 새로고침 한 번에 일자·장소 일출·일몰이 보인다(ETL 대기 없음)', async ({ page }) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-040'), start: D(1), end: D(1) });
    trips.track(id);
    await loadTripView(page, id);
    await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    expect(day1.rise_set?.status, 'day rise_set').toBe('success');
    const article = await openDay(page, 1);
    const daySun = riseSuccess(article);
    await expect(daySun).toBeVisible();
    await expect(article.getByTestId('trip-day-rise-set-pending')).toHaveCount(0);

    const poi = day1.pois[0]!;
    const coord = poiCoord(poi);
    expect(coord, '장소 좌표').not.toBeNull();
    const noaa = noaaSunTimesKst(coord!.lat, coord!.lon, day1.effective_date!)!;
    const row = poiRow(page, '고씨');
    const poiSun = row.getByTestId('trip-poi-rise-set');
    await expect(poiSun).toBeVisible();
    const ui = parseRiseSet(await poiSun.innerText());
    annotate(`POI UI ${ui.sunrise}/${ui.sunset} NOAA ${noaa.sunrise}/${noaa.sunset}`);
    expect(clockDiffMin(hhmmToMin(ui.sunrise!)!, noaa.sunriseMin)).toBeLessThanOrEqual(3);
    expect(clockDiffMin(hhmmToMin(ui.sunset!)!, noaa.sunsetMin)).toBeLessThanOrEqual(3);
    // 장소 하나뿐이면 일자 centroid = 그 장소라 같은 값이다.
    const dayUi = parseRiseSet(await daySun.innerText());
    expect({ sunrise: dayUi.sunrise, sunset: dayUi.sunset }).toEqual({ sunrise: ui.sunrise, sunset: ui.sunset });
    await shot(page, 'WX-040', 'sun-immediate');
  });

  test('TRIP-071 일자 목록에 요일, 토요일·일요일·공휴일 강조와 공휴일 이름', async ({ page }) => {
    await loginAsUser(page);
    // 2026-12-25(금, 기독탄신일) · 26(토) · 27(일) · 28(월)
    const { id } = await createTrip(page, { title: wxTitle('TRIP-071'), start: '2026-12-25', end: '2026-12-28' });
    trips.track(id);
    const view = await loadTripView(page, id);
    const expected: Record<number, { weekday: string; tone: string | null }> = {
      1: { weekday: '(금)', tone: 'holiday' },
      2: { weekday: '(토)', tone: 'saturday' },
      3: { weekday: '(일)', tone: 'holiday' },
      4: { weekday: '(월)', tone: null },
    };
    for (const [index, want] of Object.entries(expected)) {
      const article = page
        .getByRole('tab', { name: `${index}일차`, exact: true })
        .locator('xpath=ancestor::article[1]');
      const date = article.getByTestId('trip-day-date').first();
      await expect(date.getByTestId('trip-day-weekday')).toHaveText(want.weekday);
      if (want.tone) await expect(date).toHaveAttribute('data-day-tone', want.tone);
      else await expect(date).not.toHaveAttribute('data-day-tone');
    }
    const day1 = dayOf(view, 1);
    const names = day1.holidays?.map((h) => h.name) ?? [];
    annotate(`12-25 holidays=${JSON.stringify(names)}`);
    expect(names.length, 'KASI 특일(기독탄신일)이 적재돼 있어야 한다').toBeGreaterThan(0);
    const article1 = page.getByRole('tab', { name: '1일차', exact: true }).locator('xpath=ancestor::article[1]');
    await expect(article1.getByTestId('trip-day-holiday')).toContainText(names[0]!);
    await shot(page, 'TRIP-071', 'weekday-holiday');
  });
});
