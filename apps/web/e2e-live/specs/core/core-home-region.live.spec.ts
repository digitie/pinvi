/**
 * CORE — 개인 홈 '다녀온 지역'의 장소 시도(서버 역지오코딩, apps/api/app/services/poi_region.py).
 * 지도 검색으로 담은 장소는 snapshot에 좌표뿐이다. 서버가 장소를 담은 뒤 kor-travel-geo로 시도를 찾아 둔다.
 */
import { expect, test } from '@playwright/test';
import {
  apiBaseURL,
  createTrip,
  deleteTrip,
  e2ePrefix,
  loginAsUser,
  searchAndAddPlace,
  shot,
  withRateLimitRetry,
} from '../../helpers/live';
import { D } from '../../helpers/weather';

test.describe('CORE personal home region', () => {
  test('CORE-038 지역 메모 없는 지난 여행에 담은 장소도 시도가 잡힌다', async ({ page }) => {
    test.skip(test.info().project.name === 'mobile', 'desktop에서만(데이터 변경)');
    await loginAsUser(page);
    const title = `${e2ePrefix} CORE-038 시도 ${Date.now()}`;
    // 지역 메모를 비운다 — 시도는 장소 좌표 역지오코딩에서만 나올 수 있다.
    const { id } = await createTrip(page, { title, region: '', start: D(-2), end: D(-1) });
    try {
      await page.goto(`/trips/${id}`);
      await searchAndAddPlace(page, 1, '경포해변', (t) => t.includes('경포'));
      const api = await apiBaseURL(page);
      // 배경 조회는 응답 뒤에 끝난다 — 홈 집계에 반영될 때까지 짧게 기다린다.
      await expect
        .poll(
          async () => {
            const res = await withRateLimitRetry('GET /users/me/home', () =>
              page.context().request.get(`${api}/users/me/home`),
            );
            const body = (await res.json()) as {
              data: { recent_trips: { title: string; region_name: string | null }[] };
            };
            return body.data.recent_trips.find((trip) => trip.title === title)?.region_name ?? null;
          },
          { timeout: 30_000, intervals: [1_000, 2_000, 5_000] },
        )
        .toBe('강원');
      await page.goto('/home');
      await expect(page.getByTestId('home-regions')).toContainText('강원');
      await shot(page, 'CORE-038', 'home-region');
    } finally {
      await deleteTrip(page, id);
    }
  });
});
