/**
 * WX — 장소 목록 이름 옆 현재 날씨 배지 + 날씨 예보 팝업 (live, prod, no mocks).
 * Cases: WX-041, WX-042.
 * Selectors/text: components/weather/WeatherBadge.tsx (weather-badge*), WeatherForecastPopup.tsx
 * (weather-forecast-popup, weather-current, weather-hourly/weather-hour, weather-daily/weather-day),
 * TripPoiList.tsx. API: GET /trips/{id}/pois/{poi}/weather (배포 뒤에만 존재).
 */
import { expect, test, type Page } from '@playwright/test';
import { createTrip, loginAsUser, poiRows, searchAndAddPlace, shot } from '../../helpers/live';
import { D, annotate, onDesktop, onMobile, openDay, useTripCleanup, wxTitle } from '../../helpers/weather';

async function expectBadgeAndPopup(page: Page, caseId: string) {
  const row = poiRows(page).first();
  const badge = row.getByTestId('weather-badge');
  // 장소 날씨는 첫 조회(위치 해석 캐시 미스)에 빈 카드일 수 있다 — 배지가 없으면 한 번 새로고침한다.
  // `isVisible({ timeout })`은 기다리지 않는다(Playwright는 그 timeout을 무시한다) — 실제로 기다린다.
  const appeared = await badge.waitFor({ state: 'visible', timeout: 30_000 }).then(
    () => true,
    () => false,
  );
  if (!appeared) {
    annotate('첫 조회 빈 카드 — 새로고침 후 재확인');
    await page.reload();
    await openDay(page, 1);
  }
  await expect(badge).toBeVisible({ timeout: 45_000 });
  await expect(badge.getByTestId('weather-badge-temp')).toHaveText(/^-?\d+°$/);
  await expect(badge).toHaveAccessibleName(/현재 .+날씨 예보 열기/);
  await expect(badge.locator('svg[data-weather-condition]')).toHaveCount(1);
  await expect.soft(badge.getByTestId('weather-badge-range'), '오늘 최고/최저').toHaveText(/^-?\d+°\/-?\d+°$/);
  const rowSelectedBefore = await row.locator('[aria-current="true"]').count();

  await badge.click();
  const popup = page.getByTestId('weather-forecast-popup');
  await expect(popup).toBeVisible();
  await expect(popup.getByTestId('weather-current-temp')).toHaveText(/^-?\d+°$/);
  await expect.soft(popup.getByTestId('weather-hourly'), '시간별 예보 띠').toBeVisible();
  await expect.soft(popup.getByTestId('weather-hour').first()).toContainText(/(지금|\d+시)/);
  await expect.soft(popup.getByTestId('weather-daily'), '일별 최고/최저').toBeVisible();
  await expect.soft(popup.getByTestId('weather-day').first()).toContainText('오늘');
  await expect(popup).not.toContainText(/deg_c|FEELS_LIKE|T1H|TMP/);
  await expect(popup).toContainText(/출처:/);
  await shot(page, caseId, 'weather-popup');
  // 배지를 눌러도 행 선택은 바뀌지 않는다.
  await page.keyboard.press('Escape');
  await expect(popup).toBeHidden();
  expect(await row.locator('[aria-current="true"]').count()).toBe(rowSelectedBefore);
}

test.describe('weather · place badge', () => {
  test.setTimeout(180_000);
  const trips = useTripCleanup();

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('WX-041 장소 이름 옆 현재 날씨 배지 → 예보 팝업(데스크톱)', async ({ page, isMobile }) => {
    test.skip(onMobile({ isMobile }), '데스크톱 전용(모바일은 WX-042)');
    const { id } = await createTrip(page, { title: wxTitle('WX-041'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    await openDay(page, 1);
    await expectBadgeAndPopup(page, 'WX-041');
  });

  test('WX-042 모바일: 배지 탭 → 하단 시트 예보, 행 선택 없음', async ({ page, isMobile }) => {
    test.skip(onDesktop({ isMobile }), '모바일 전용');
    const { id } = await createTrip(page, { title: wxTitle('WX-042'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    await openDay(page, 1);
    await expectBadgeAndPopup(page, 'WX-042');
  });
});
