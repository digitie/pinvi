/**
 * SHR 모바일(390x844) — 공유 페이지 레이아웃, 드로어에서 링크 만들기.
 * mobile 프로젝트에서만 실행한다(데스크톱 프로젝트에서는 skip).
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, searchAndAddPlace, shot, waitForMapIdle } from '../../helpers/live';
import {
  createShareLink,
  expectSharedReadOnly,
  gotoTrip,
  openSharedInFreshContext,
  openTripTab,
  uniqueTitle,
} from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 모바일 (390x844)', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile 프로젝트 전용');

  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-013 공유 페이지 모바일 렌더링 — 세로 스택, 가로 스크롤 없음 (heritage: 소수서원)', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('013');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    const placeName = await searchAndAddPlace(page, 1, '소수서원');
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const fresh = await openSharedInFreshContext(browser, id, link.token, {
      viewport: { width: 390, height: 844 },
    });
    try {
      expect(fresh.apiStatus).toBe(200);
      await expectSharedReadOnly(fresh.page, title);
      await expect(fresh.page.getByTestId('trip-poi-list')).toContainText(placeName);
      await waitForMapIdle(fresh.page);

      // 세로 스택: 지도 영역이 장소 목록보다 위에 온다.
      const mapBox = await fresh.page.getByRole('region', { name: '여행 지도' }).boundingBox();
      const listBox = await fresh.page
        .getByRole('complementary', { name: '장소 목록' })
        .boundingBox();
      expect(mapBox && listBox && listBox.y >= mapBox.y + mapBox.height - 1).toBe(true);
      // 가로 오버플로 없음.
      const overflow = await fresh.page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
      // 일자 탭은 터치 타깃 높이(44px 이상)를 유지한다.
      const tabBox = await fresh.page.getByRole('tab', { name: /1일차/ }).boundingBox();
      expect(tabBox && tabBox.height >= 44).toBe(true);
      await shot(fresh.page, 'SHR-013', '01-mobile-shared');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-014 모바일 드로어에서 공유 링크 만들기', async ({ page }) => {
    const title = uniqueTitle('014');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);

    await expect(page.getByTestId('trip-top-panel')).toBeVisible();
    await expect(page.getByRole('tab', { name: '공유' })).toBeHidden();
    await page.getByRole('button', { name: '패널 열기' }).click();
    await expect(page.getByTestId('trip-detail-panel')).toBeVisible();
    await expect(page.getByTestId('trip-realtime-status')).toContainText(/실시간 .+ · 접속 \d+명/);
    await page.getByRole('tab', { name: '공유' }).click();
    await expect(page.getByRole('tabpanel', { name: '공유' })).toBeVisible();

    const link = await createShareLink(page);
    expect(link.tripId).toBe(id);
    await expect(page.getByTestId('share-link-list')).toContainText('활성');
    await shot(page, 'SHR-014', '01-mobile-drawer-share');

    // 드로어 닫기 → 지도가 다시 전면.
    await page.getByRole('button', { name: '패널 닫기' }).first().click();
    await expect(page.getByTestId('trip-detail-panel')).toBeHidden();
  });
});
