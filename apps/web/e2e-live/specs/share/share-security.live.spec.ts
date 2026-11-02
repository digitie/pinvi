/**
 * SHR 보안 네거티브 — 토큰 유출(URL/Referer/WebSocket), 타인 여행 id, 비로그인 접근.
 */
import { expect, test } from '@playwright/test';
import { baseURL, createTrip, deleteTrip, loginAsUser, shot, waitForMapIdle } from '../../helpers/live';
import {
  apiBaseFromPage,
  createShareLink,
  gotoTrip,
  isMobileProject,
  openSharedInFreshContext,
  openTripTab,
  redact,
  sharedApiRe,
  sharedPath,
  uniqueTitle,
  user2Context,
} from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 보안 네거티브 (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, '데스크톱 전용');

  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-009 공유 페이지에서 토큰은 페이지 URL과 공유 API 호출 밖으로 새지 않는다', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('009');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(200);
      await expect(fresh.page.getByRole('heading', { level: 1, name: title })).toBeVisible();
      await waitForMapIdle(fresh.page);
      // 지도 타일·정적 자원 요청까지 충분히 쌓인 뒤 검사한다.
      const webHost = new URL(baseURL).host;
      const apiRe = sharedApiRe(id);

      const urlLeaks = fresh.requests
        .filter((r) => r.url.includes(link.token))
        .filter((r) => {
          const u = new URL(r.url);
          const isPageNav = u.host === webHost && u.pathname === sharedPath(id, link.token);
          const isSharedApi = apiRe.test(u.pathname) && u.pathname.endsWith(link.token);
          return !(isPageNav || isSharedApi);
        })
        .map((r) => redact(r.url, link.token));
      expect(urlLeaks, 'token이 허용된 두 요청 외의 URL에 나타남').toEqual([]);

      const refererLeaks = fresh.requests
        .filter((r) => new URL(r.url).host !== webHost)
        .filter((r) => r.referer?.includes(link.token))
        .map((r) => new URL(r.url).host);
      expect(refererLeaks, 'cross-origin 요청의 Referer에 token이 실림').toEqual([]);

      // 페이지 본문(코드/스크립트 제외한 가시 텍스트)에도 토큰 원문이 없어야 한다.
      const bodyText = (await fresh.page.locator('body').innerText()) ?? '';
      expect(bodyText.includes(link.token)).toBe(false);
      await shot(fresh.page, 'SHR-009', '01-no-leak');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-010 소유자 화면: WebSocket URL에 token 쿼리 없음, 공유 토큰은 요청 URL에 안 실림', async ({
    page,
  }) => {
    const title = uniqueTitle('010');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);

    const wsUrls: string[] = [];
    page.on('websocket', (ws) => wsUrls.push(ws.url()));
    const requestUrls: string[] = [];
    page.on('request', (request) => requestUrls.push(request.url()));

    await gotoTrip(page, id, title);
    await expect(page.getByTestId('trip-realtime-status')).toContainText('연결됨');
    expect(wsUrls.some((u) => /\/ws\/trips\//.test(u))).toBe(true);
    expect(wsUrls.filter((u) => /[?&]token=/.test(u))).toEqual([]);
    expect(wsUrls.filter((u) => /pinvi_access/.test(u))).toEqual([]);

    await openTripTab(page, '공유');
    const link = await createShareLink(page);
    // 생성 직후 소유자 화면이 보내는 요청(reload 등)에 토큰이 섞이면 안 된다.
    await expect(page.getByTestId('share-link-list')).toContainText('활성');
    const leaks = requestUrls.filter((u) => u.includes(link.token)).map((u) => redact(u, link.token));
    expect(leaks).toEqual([]);
    // 응답 본문이 아닌 화면에는 1회성 배너에만 표시된다(목록에는 token 없음).
    await expect(page.getByTestId('share-link-list')).not.toContainText(link.token);
  });

  test('SHR-017 존재하지 않는 여행 id → 404 안내, 비로그인 /trips/{id} → 로그인으로', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('017');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);

    const randomId = '00000000-0000-4000-8000-00000000e2e0';
    await page.goto(`/trips/${randomId}`);
    const error = page.getByTestId('trip-detail-error');
    await expect(error).toBeVisible();
    await expect(error).toContainText('여행을 찾을 수 없습니다');
    await expect(page.getByRole('link', { name: '여행 목록' })).toBeVisible();
    await shot(page, 'SHR-017', '01-unknown-trip');

    const anon = await browser.newContext({ baseURL });
    try {
      const anonPage = await anon.newPage();
      await anonPage.goto(`/trips/${id}`);
      await expect(anonPage).toHaveURL(/\/login(?:[?#].*)?$/);
      await expect(anonPage.getByRole('heading', { name: title })).toHaveCount(0);
      await expect(anonPage.getByTestId('login-form')).toBeVisible();
    } finally {
      await anon.close();
    }
  });

  test('SHR-018 다른 사용자(test2)의 여행 id로 접근하면 403 권한 안내', async ({ page, browser }) => {
    const apiBase = apiBaseFromPage(page);
    const user2 = await user2Context(browser);
    let otherTripId: string | null = null;
    try {
      const title = uniqueTitle('018-user2');
      const trip = await createTrip(user2.page, { title, start: '2026-11-20', end: '2026-11-20' });
      otherTripId = trip.id;

      await page.goto(`/trips/${otherTripId}`);
      const error = page.getByTestId('trip-detail-error');
      await expect(error).toBeVisible();
      await expect(error).toContainText('이 여행에 대한 권한이 없습니다');
      await expect(page.getByRole('heading', { name: title })).toHaveCount(0);
      await expect(page.getByTestId('trip-detail-map')).toHaveCount(0);
      await shot(page, 'SHR-018', '01-forbidden');

      // 하위 API도 거부: 댓글 목록을 세션 쿠키로 직접 호출. origin은 페이지의 첫 API 요청에서 유도.
      const commentsRes = await page.request.get(`${await apiBase()}/trips/${otherTripId}/comments`);
      if (process.env.PINVI_E2E_API_URL) expect(commentsRes.status()).toBe(403);
      else expect([401, 403, 404]).toContain(commentsRes.status());
    } finally {
      if (otherTripId) await deleteTrip(user2.page, otherTripId).catch(() => undefined);
      await user2.context.close();
    }
  });
});
