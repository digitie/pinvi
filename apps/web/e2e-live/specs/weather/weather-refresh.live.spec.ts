/**
 * WX — 날씨 새로고침 버튼(2026-11-16 소유자 요청 15).
 * Cases: WX-045.
 * Facts:
 *  - apps/web/components/trips/TripWeatherSummary.tsx — 상태 문구 옆 'trip-weather-refresh', 결과 'trip-weather-refresh-message'.
 *  - apps/api/app/api/v1/trip_weather.py — POST /trips/{id}/days/{n}/weather/refresh, 같은 feature 60초 쿨다운.
 * 30일 뒤 날짜는 예보 범위 밖이라 언제나 "이 날짜의 날씨 정보가 없습니다."가 나온다(결정적 빈 상태).
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  D,
  TEXT,
  annotate,
  daySection,
  loadTripView,
  onMobile,
  openDay,
  poiRow,
  poiSection,
  useTripCleanup,
  wxTitle,
} from '../../helpers/weather';

test.describe('weather · 새로고침', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용');
  const trips = useTripCleanup();

  test('WX-045 날씨 없음 문구 옆 새로고침 → POST refresh 200, 같은 장소 재시도는 쿨다운 안내', async ({ page }) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-045'), start: D(30), end: D(30) });
    trips.track(id);
    await loadTripView(page, id);
    await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    const article = await openDay(page, 1);
    const day = daySection(article);
    await expect(day).toContainText(TEXT.noData);
    const button = day.getByRole('button', { name: '날씨 새로고침' });
    await expect(button).toBeVisible();

    const first = page.waitForResponse(
      (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === `/trips/${id}/days/1/weather/refresh`,
    );
    await button.click();
    const res = await first;
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { data: Record<string, number | null> };
    annotate(`refresh#1 ${JSON.stringify(body.data)}`);
    expect((body.data.refreshed ?? 0) + (body.data.cooldown ?? 0) + (body.data.no_data ?? 0)).toBe(1);
    await expect(day.getByTestId('trip-weather-refresh-message')).toBeVisible();
    // 30일 뒤는 예보 범위 밖 — 다시 확인해도 비어 있다.
    await expect(daySection(article)).toContainText(TEXT.noData);
    await shot(page, 'WX-045', 'refreshed');

    // 같은 장소(장소 날씨 버튼)는 60초 안이라 쿨다운이다 — Map을 다시 부르지 않는다.
    const place = poiSection(poiRow(page, '고씨'));
    const second = page.waitForResponse(
      (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === `/trips/${id}/days/1/weather/refresh`,
    );
    await place.getByRole('button', { name: '날씨 새로고침' }).click();
    const again = (await (await second).json()) as { data: { cooldown: number; retry_after_seconds: number | null } };
    expect(again.data.cooldown).toBe(1);
    expect(again.data.retry_after_seconds).toBeGreaterThan(0);
    await expect(place.getByTestId('trip-weather-refresh-message')).toContainText('초 뒤 다시 시도');
  });
});
