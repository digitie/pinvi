/**
 * WX — 날씨 새로고침 버튼(2026-11-16 소유자 요청 15).
 * Cases: WX-045.
 * Facts:
 *  - apps/web/components/trips/TripWeatherSummary.tsx — 상태 문구 옆 'trip-weather-refresh', 결과 'trip-weather-refresh-message'.
 *  - apps/api/app/api/v1/trip_weather.py — POST /trips/{id}/days/{n}/weather/refresh, 같은 feature 60초 쿨다운.
 * 30일 뒤 날짜는 예보 범위 밖이라 2026-11-17(결정 3)부터 '예보는 N일 앞(M월 D일)까지만 제공됩니다.'만 보이고
 * 새로고침 버튼은 없다. 버튼 동작은 단위 시험(tripWeatherRefresh·forecastHorizon), API 계약은 여기서 직접 부른다.
 */
import { expect, test } from '@playwright/test';
import { apiBaseURL, createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  BEYOND_FORECAST_RE,
  D,
  annotate,
  beyondForecast,
  dayOf,
  daySection,
  loadTripView,
  onMobile,
  openDay,
  reloadTripView,
  useTripCleanup,
  wxTitle,
} from '../../helpers/weather';

test.describe('weather · 새로고침', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용');
  const trips = useTripCleanup();

  test('WX-045 예보 범위 밖은 새로고침 없이 범위 안내, refresh API는 200·같은 장소 60초 쿨다운', async ({ page }) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-045'), start: D(30), end: D(30) });
    trips.track(id);
    await loadTripView(page, id);
    await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const poi = day1.pois[0]!;
    const article = await openDay(page, 1);
    const day = daySection(article);
    // 2026-11-17 결정 3: 30일 뒤는 예보 범위 밖 — 전용 안내만, 다시 물어도 같아서 새로고침 버튼이 없다.
    const res = day1.weather_by_feature_id[poi.feature_id!];
    annotate(`resolution=${JSON.stringify(res)}`);
    expect(beyondForecast(res, day1.effective_date!), 'no_data.forecast_until').toBeTruthy();
    await expect(day.locator('p').first()).toHaveText(BEYOND_FORECAST_RE);
    await expect(day.getByRole('button', { name: '날씨 새로고침' })).toHaveCount(0);
    await shot(page, 'WX-045', 'beyond-forecast');

    // 버튼이 뜨는 '범위 안 빈 날짜'는 live에서 결정적으로 만들 수 없어 API 계약은 직접 부른다(버튼 동작은 단위 시험).
    const api = await apiBaseURL(page);
    const url = `${api}/trips/${id}/days/1/weather/refresh`;
    const first = await page.context().request.post(url, { data: { poi_id: poi.poi_id } });
    expect(first.status()).toBe(200);
    const body = (await first.json()) as { data: Record<string, number | null> };
    annotate(`refresh#1 ${JSON.stringify(body.data)}`);
    expect((body.data.refreshed ?? 0) + (body.data.cooldown ?? 0) + (body.data.no_data ?? 0)).toBe(1);
    const again = (await (await page.context().request.post(url, { data: { poi_id: poi.poi_id } })).json()) as {
      data: { cooldown: number; retry_after_seconds: number | null };
    };
    expect(again.data.cooldown).toBe(1);
    expect(again.data.retry_after_seconds).toBeGreaterThan(0);
  });
});
