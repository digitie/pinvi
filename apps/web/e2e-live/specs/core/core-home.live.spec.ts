/**
 * CORE — 개인 홈(/home): 로고·'홈'이 로그인 사용자를 개인 홈으로, 익명 사용자를 로그인으로 보낸다.
 * Selectors: apps/web/components/home/PersonalHome.tsx, components/app/AppShell.tsx,
 * components/app/SignedInHomeRedirect.tsx, API GET /users/me/home (apps/api/app/services/user_home.py).
 */
import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  apiBaseURL,
  createTrip,
  deleteTrip,
  e2ePrefix,
  isMobile,
  loginAsUser,
  user2Context,
  user2Email,
  searchAndAddPlace,
  shot,
  withRateLimitRetry,
} from '../../helpers/live';
import { D } from '../../helpers/weather';

type HomeStats = {
  trip_count: number;
  completed_trip_count: number;
  travel_day_count: number;
  visited_place_count: number;
  region_count: number;
};

async function homeStats(page: Page): Promise<HomeStats> {
  const api = await apiBaseURL(page);
  const res = await withRateLimitRetry('GET /users/me/home', () =>
    page.context().request.get(`${api}/users/me/home`),
  );
  expect(res.status(), 'GET /users/me/home').toBe(200);
  return ((await res.json()) as { data: { stats: HomeStats } }).data.stats;
}

async function expectHomeRendered(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/home(?:[?#].*)?$/, { timeout: 20_000 });
  const root = page.getByTestId('personal-home');
  await expect(root.getByRole('heading', { name: '내 여행', level: 1 })).toBeVisible();
  const stats = page.getByTestId('home-stats');
  await expect(stats).toBeVisible({ timeout: 20_000 });
  for (const id of ['home-stat-trips', 'home-stat-days', 'home-stat-places', 'home-stat-regions']) {
    await expect(page.getByTestId(id)).toContainText(/\d/);
  }
  await expect(page.getByTestId('home-stat-regions')).toContainText('/17');
}

test.describe('CORE personal home', () => {
  test('CORE-032 로그인 사용자의 로고는 개인 홈으로 간다', async ({ page }, testInfo) => {
    await loginAsUser(page);
    await page.goto('/trips');
    await expect(page.getByRole('heading', { name: '여행', exact: true })).toBeVisible();
    const logo = page.getByRole('link', { name: 'Pinvi 홈' });
    await expect(logo).toHaveAttribute('href', '/home');
    await logo.click();
    await expectHomeRendered(page);
    await expect(page).not.toHaveURL(/\/login/);
    await shot(page, 'CORE-032', isMobile(testInfo) ? 'home-mobile' : 'home-desktop');
  });

  test('CORE-033 로그인 사용자의 홈 메뉴와 랜딩의 내 홈은 개인 홈으로 간다', async ({
    page,
  }, testInfo) => {
    await loginAsUser(page);
    await page.goto('/map');
    if (isMobile(testInfo)) {
      // 모바일 하단 탭바의 첫 탭이 홈이다(2026-11-17).
      await page.getByTestId('app-nav--home-mobile').click();
    } else {
      await page.getByTestId('app-nav--home').click();
    }
    await expectHomeRendered(page);
    if (!isMobile(testInfo)) {
      await expect(page.getByTestId('app-nav--home')).toHaveAttribute('aria-current', 'page');
    }
    // 마케팅 랜딩은 로그인 사용자에게 로그인·시작하기 대신 '내 홈'을 보인다.
    await page.goto('/');
    const myHome = page.getByTestId('landing-my-home');
    await expect(myHome).toBeVisible({ timeout: 20_000 });
    await myHome.click();
    await expectHomeRendered(page);
  });

  test('CORE-034 익명 사용자 — /home은 로그인으로, 랜딩은 그대로', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('home-hero')).toBeVisible();
    // 랜딩의 로그인 확인(GET /auth/me 401)이 끝나도 로그인·시작하기가 그대로다.
    await page.waitForLoadState('networkidle');
    await expect(page.getByTestId('landing-my-home')).toHaveCount(0);
    await expect(page.getByRole('banner').getByRole('link', { name: '로그인' })).toBeVisible();
    await page.goto('/home');
    await expect(page).toHaveURL(/\/login\?next=%2Fhome/, { timeout: 20_000 });
    await shot(page, 'CORE-034', 'login');
  });

  test('CORE-035 지난 여행에 장소를 담으면 홈 통계와 최근 여행에 반영된다', async ({ page }) => {
    test.skip(test.info().project.name === 'mobile', '통계 반영은 desktop에서만(같은 계정 데이터)');
    await loginAsUser(page);
    const before = await homeStats(page);
    const title = `${e2ePrefix} CORE-035 홈 통계 ${Date.now()}`;
    const { id } = await createTrip(page, { title, region: '강릉', start: D(-2), end: D(-1) });
    try {
      await page.goto(`/trips/${id}`);
      await searchAndAddPlace(page, 1, '경포해변', (t) => t.includes('경포'));
      const after = await homeStats(page);
      expect(after.trip_count).toBe(before.trip_count + 1);
      expect(after.completed_trip_count).toBe(before.completed_trip_count + 1);
      expect(after.travel_day_count).toBeGreaterThanOrEqual(before.travel_day_count);
      expect(after.visited_place_count).toBeGreaterThanOrEqual(
        Math.max(1, before.visited_place_count),
      );
      expect(after.region_count).toBeGreaterThanOrEqual(1);

      await page.goto('/home');
      await expectHomeRendered(page);
      await expect(page.getByTestId('home-recent')).toContainText(title);
      await expect(page.getByTestId('home-regions')).toContainText('강원');
      await expect(page.getByTestId('home-stat-trips')).toContainText(
        String(after.completed_trip_count),
      );
      await shot(page, 'CORE-035', 'home-after');
    } finally {
      await deleteTrip(page, id);
    }
  });

  test('CORE-036 모바일 하단 탭바 — 홈이 첫 탭, 5칸이 320·390px에서 44px 이상', async ({
    page,
  }, testInfo) => {
    test.skip(!isMobile(testInfo), 'mobile project only');
    await loginAsUser(page);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/trips');
      const tabbar = page.locator('nav[aria-label="주요 메뉴"]');
      await expect(tabbar).toBeVisible();
      const cells: Locator = tabbar.locator(':scope > ul > li');
      await expect(cells).toHaveCount(5);
      await expect(cells).toHaveText([/홈/, /여행/, /추천/, /지도/, /더보기/]);
      for (let i = 0; i < 5; i += 1) {
        const box = await cells.nth(i).locator('a, button').first().boundingBox();
        expect(box, `cell ${i} @${width}`).not.toBeNull();
        expect(box!.width, `cell ${i} width @${width}`).toBeGreaterThanOrEqual(44);
        expect(box!.height, `cell ${i} height @${width}`).toBeGreaterThanOrEqual(44);
      }
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow @${width}`).toBeLessThanOrEqual(0);
      await shot(page, 'CORE-036', `tabbar-${width}`);
    }
    // 파일은 더보기로 갔다.
    await page.getByTestId('app-nav-more-toggle').click();
    await page.getByTestId('app-nav--files-mobile').click();
    await expect(page).toHaveURL(/\/files$/);
  });

  test('CORE-037 동행으로 참여한 여행이 개인 홈 통계와 목록에 동행 표시로 보인다', async ({
    page,
    browser,
  }) => {
    test.skip(test.info().project.name === 'mobile', 'desktop에서만(두 계정 데이터 변경)');
    await loginAsUser(page);
    const title = `${e2ePrefix} CORE-037 동행 ${Date.now()}`;
    const { id } = await createTrip(page, { title, region: '경주', start: D(-3), end: D(-2) });
    const friend = await user2Context(browser);
    try {
      const before = await homeStats(friend.page);
      const api = await apiBaseURL(page);
      const invited = await withRateLimitRetry(`POST /trips/${id}/members`, () =>
        page.context().request.post(`${api}/trips/${id}/members`, {
          data: { email: user2Email(), role: 'viewer' },
        }),
      );
      expect(invited.status(), 'POST members').toBe(201);
      const after = await homeStats(friend.page);
      expect(after.trip_count).toBe(before.trip_count + 1);
      expect(after.completed_trip_count).toBe(before.completed_trip_count + 1);

      await friend.page.goto('/home');
      await expectHomeRendered(friend.page);
      const row = friend.page
        .getByTestId('home-recent')
        .getByRole('listitem')
        .filter({ hasText: title });
      await expect(row).toBeVisible();
      await expect(row.getByTestId('home-trip-joined')).toHaveText('동행');
      await shot(friend.page, 'CORE-037', 'friend-home');
    } finally {
      await friend.context.close();
      await deleteTrip(page, id);
    }
  });
});
