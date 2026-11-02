/**
 * SHR 실시간 표시기 + 여행 복사.
 */
import { expect, test } from '@playwright/test';
import { baseURL, createTrip, deleteTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import { gotoTrip, isMobileProject, openTripTab, uniqueTitle } from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 실시간·복사', () => {
  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-023 실시간 표시기 "실시간 연결됨 · 접속 N명" (desktop+mobile)', async ({ page, browser }) => {
    const title = uniqueTitle('023');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);

    const wsUrls: string[] = [];
    page.on('websocket', (ws) => wsUrls.push(ws.url()));
    await gotoTrip(page, id, title);
    if (isMobileProject()) await page.getByRole('button', { name: '패널 열기' }).click();

    const status = page.getByTestId('trip-realtime-status').first();
    await expect(status).toContainText('실시간 연결됨');
    await expect(status).toContainText(/접속 \d+명/);
    expect(wsUrls.some((u) => new RegExp(`/ws/trips/${id}`).test(u))).toBe(true);
    await expect(page.getByTestId('trip-realtime-reconnect')).toHaveCount(0);
    await shot(page, 'SHR-023', '01-realtime-connected');

    // 같은 계정의 두 번째 컨텍스트가 붙어도 양쪽 모두 "연결됨"을 유지한다.
    const other = await browser.newContext({ baseURL });
    try {
      const otherPage = await other.newPage();
      await loginAsUser(otherPage);
      await gotoTrip(otherPage, id, title);
      if (isMobileProject()) await otherPage.getByRole('button', { name: '패널 열기' }).click();
      await expect(otherPage.getByTestId('trip-realtime-status').first()).toContainText(
        '실시간 연결됨',
      );
      await expect(status).toContainText('실시간 연결됨');
      await expect(status).toContainText(/접속 \d+명/);
    } finally {
      await other.close();
    }
    await expect(status).toContainText('실시간 연결됨');
  });

  test('SHR-031 여행 복사 — "<제목> copy" 초안 생성, 일자·장소 복제 (heritage: 경주 불국사)', async ({
    page,
  }) => {
    test.skip(({ isMobile }) => isMobile, '데스크톱 전용');
    const title = uniqueTitle('031');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-21' });
    created.push(id);
    await gotoTrip(page, id, title);
    const placeName = await searchAndAddPlace(page, 1, '경주 불국사');

    await page.getByTestId('trip-actions').getByRole('button', { name: '복사' }).click();
    await expect(page).toHaveURL(new RegExp(`/trips/(?!${id})[0-9a-f-]{36}`));
    const copyId = /\/trips\/([0-9a-f-]{36})/i.exec(page.url())?.[1];
    expect(copyId).toBeTruthy();
    created.push(copyId!);

    const copyTitle = `${title} copy`;
    await expect(page.getByRole('heading', { name: copyTitle }).first()).toBeVisible();
    await expect(page.getByTestId('trip-top-panel')).toContainText('초안');
    await expect(page.getByTestId('trip-top-panel')).toContainText('2일 · 1개 장소');
    await expect(page.getByTestId('trip-layer-list')).toContainText(placeName);
    // 복사본에는 공유 링크·동행이 따라오지 않는다.
    await openTripTab(page, '공유');
    await expect(page.getByTestId('share-link-list')).toHaveCount(0);
    await openTripTab(page, '동행');
    await expect(page.getByTestId('companion-list')).toHaveCount(0);
    await shot(page, 'SHR-031', '01-copied-trip');

    // 원본은 그대로.
    await gotoTrip(page, id, title);
    await expect(page.getByTestId('trip-top-panel')).toContainText('2일 · 1개 장소');
  });
});
