/**
 * SHR 공유 링크 — 생성/열람/철회/재생성/만료/권한별/복사/열기/다일자/날씨 중립 텍스트/삭제된 여행.
 * 데스크톱 1440x900 기준. mobile 태그 케이스는 share-mobile.live.spec.ts.
 */
import { expect, test } from '@playwright/test';
import {
  baseURL,
  createTrip,
  deleteTrip,
  loginAsUser,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
} from '../../helpers/live';
import {
  createShareLink,
  expectSharedError,
  expectSharedReadOnly,
  gotoTrip,
  openSharedInFreshContext,
  openTripTab,
  shareSection,
  sharedPath,
  uniqueTitle,
} from '../../helpers/share';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('SHR 공유 링크 (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, '데스크톱 전용 — mobile 케이스는 share-mobile.live.spec.ts');

  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) {
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('SHR-001 공유 링크 생성 — 1회성 URL 배너와 목록 상태', async ({ page }) => {
    const title = uniqueTitle('001');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-21' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');

    const link = await createShareLink(page, { visibility: 'view_only' });
    expect(link.tripId).toBe(id);
    expect(link.url.startsWith(`${baseURL}${sharedPath(id, '')}`)).toBe(true);
    expect(link.token.length).toBeGreaterThanOrEqual(32);

    const banner = page.getByTestId('new-share-url');
    await expect(banner.getByRole('button', { name: '링크 복사' })).toBeVisible();
    await expect(banner.getByRole('link', { name: '열기' })).toHaveAttribute(
      'href',
      sharedPath(id, link.token),
    );

    const list = page.getByTestId('share-link-list');
    await expect(list.getByRole('listitem')).toHaveCount(1);
    await expect(list).toContainText('보기 전용');
    await expect(list).toContainText('활성');
    await expect(list).toContainText('만료 무기한');
    await expect(list.getByRole('button', { name: '공유 링크 철회' })).toHaveCount(1);
    await shot(page, 'SHR-001', '01-share-created');
  });

  test('SHR-002 로그아웃 컨텍스트에서 공유 페이지 읽기 전용 렌더링 (heritage: 안동하회마을)', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('002');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-21' });
    created.push(id);
    await gotoTrip(page, id, title);
    const placeName = await searchAndAddPlace(page, 1, '안동하회마을');
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(200);
      await expectSharedReadOnly(fresh.page, title);
      await expect(fresh.page.getByRole('tablist', { name: '일자 선택' })).toBeVisible();
      await expect(fresh.page.getByRole('tab', { name: /1일차/ })).toHaveAttribute(
        'aria-selected',
        'true',
      );
      await expect(fresh.page.getByRole('tab', { name: /2일차/ })).toBeVisible();
      await expect(fresh.page.getByTestId('trip-poi-list')).toContainText(placeName);
      await waitForMapIdle(fresh.page);
      await expect
        .poll(() => fresh.page.getByRole('region', { name: '여행 지도' }).locator('canvas').count())
        .toBeGreaterThan(0);
      // 로그인 없이 열렸음을 확인: 인증 보호 라우트로 리다이렉트되지 않았다.
      expect(new URL(fresh.page.url()).pathname).toBe(sharedPath(id, link.token));
      await shot(fresh.page, 'SHR-002', '01-shared-readonly');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-003 철회 — 목록 상태 "철회", 철회된 링크는 404 안내', async ({ page, browser }) => {
    const title = uniqueTitle('003');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const list = page.getByTestId('share-link-list');
    await list.getByRole('button', { name: '공유 링크 철회' }).click();
    const item = list.getByRole('listitem').first();
    await expect(item).toContainText('철회');
    await expect(item.getByRole('button', { name: '공유 링크 철회' })).toHaveCount(0);
    await shot(page, 'SHR-003', '01-revoked-list');

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(404);
      await expectSharedError(fresh.page, '공유 토큰을 찾을 수 없습니다');
      await expect(fresh.page.getByRole('heading', { level: 1, name: title })).toHaveCount(0);
      await shot(fresh.page, 'SHR-003', '02-revoked-404');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-004 철회 후 재생성 — 새 링크는 열리고 옛 링크는 계속 404', async ({ page, browser }) => {
    const title = uniqueTitle('004');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const first = await createShareLink(page);
    await page.getByTestId('share-link-list').getByRole('button', { name: '공유 링크 철회' }).click();
    await expect(page.getByTestId('share-link-list').getByRole('listitem').first()).toContainText(
      '철회',
    );

    const second = await createShareLink(page);
    expect(second.token).not.toBe(first.token);
    const list = page.getByTestId('share-link-list');
    await expect(list.getByRole('listitem')).toHaveCount(2);
    await expect(list.getByRole('button', { name: '공유 링크 철회' })).toHaveCount(1);

    const newOne = await openSharedInFreshContext(browser, id, second.token);
    try {
      expect(newOne.apiStatus).toBe(200);
      await expectSharedReadOnly(newOne.page, title);
    } finally {
      await newOne.context.close();
    }
    const oldOne = await openSharedInFreshContext(browser, id, first.token);
    try {
      expect(oldOne.apiStatus).toBe(404);
      await expectSharedError(oldOne.page, '공유 토큰을 찾을 수 없습니다');
    } finally {
      await oldOne.context.close();
    }
  });

  test('SHR-005 과거 만료일로 만든 링크 — 목록 "만료", 열면 404', async ({ page, browser }) => {
    const title = uniqueTitle('005');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page, { expires: '2026-01-01' });

    const item = page.getByTestId('share-link-list').getByRole('listitem').first();
    await expect(item).toContainText('만료');
    await expect(item).toContainText('2026');
    await expect(item.getByRole('button', { name: '공유 링크 철회' })).toHaveCount(0);
    await shot(page, 'SHR-005', '01-expired-list');

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(404);
      await expectSharedError(fresh.page, '공유 토큰을 찾을 수 없습니다');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-006 "편집 가능"/"댓글 가능" 링크도 공유 페이지는 읽기 전용', async ({ page, browser }) => {
    const title = uniqueTitle('006');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const editLink = await createShareLink(page, { visibility: 'edit' });
    const commentLink = await createShareLink(page, { visibility: 'comment' });
    const list = page.getByTestId('share-link-list');
    await expect(list).toContainText('편집 가능');
    await expect(list).toContainText('댓글 가능');

    for (const link of [editLink, commentLink]) {
      const fresh = await openSharedInFreshContext(browser, id, link.token);
      try {
        expect(fresh.apiStatus).toBe(200);
        await expectSharedReadOnly(fresh.page, title);
        await expect(fresh.page.getByLabel('댓글 입력')).toHaveCount(0);
        await expect(fresh.page.getByRole('button', { name: '편집' })).toHaveCount(0);
      } finally {
        await fresh.context.close();
      }
    }
  });

  test('SHR-007 "열기"는 새 탭에서 공유 페이지를 연다', async ({ page, context }) => {
    const title = uniqueTitle('007');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      page.getByTestId('new-share-url').getByRole('link', { name: '열기' }).click(),
    ]);
    await popup.waitForLoadState();
    expect(new URL(popup.url()).pathname).toBe(sharedPath(id, link.token));
    await expectSharedReadOnly(popup, title);
    await popup.close();
  });

  test('SHR-008 "링크 복사"는 표시된 URL을 클립보드에 넣는다', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: baseURL });
    const title = uniqueTitle('008');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    await page.getByTestId('new-share-url').getByRole('button', { name: '링크 복사' }).click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe(link.url);
  });

  test('SHR-011 공유 페이지의 날씨/일출·일몰은 중립 텍스트만 (park: 설악산)', async ({
    page,
    browser,
  }) => {
    const title = uniqueTitle('011');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    const placeName = await searchAndAddPlace(page, 1, '설악산');
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(200);
      const aside = fresh.page.getByRole('complementary', { name: '장소 목록' });
      await expect(aside.getByTestId('trip-poi-list')).toContainText(placeName);

      // 날씨: 요약(값) 또는 상태(중립 안내) 중 하나가 장소마다 있다.
      const weatherBlocks = aside.locator(
        '[data-testid="trip-weather-summary"], [data-testid="trip-weather-status"]',
      );
      await expect.poll(() => weatherBlocks.count()).toBeGreaterThan(0);
      const statusTexts = await aside.getByTestId('trip-weather-status').allTextContents();
      const allowed = [
        '이 날짜의 날씨 정보가 없습니다.',
        '날씨 서비스를 일시적으로 사용할 수 없습니다.',
        '장소 상태가 종료되어 날씨를 확인할 수 없습니다.',
        '비공개 장소는 날씨를 확인할 수 없습니다.',
        '장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.',
      ];
      for (const text of statusTexts) expect(allowed).toContain(text.trim());

      // 일출/일몰: 값 표시 or "준비 중" 안내 or 미표시 — 깨진 값 금지.
      const header = fresh.page.getByTestId('trip-day-header');
      await expect(header).toBeVisible();
      const riseSet = header.getByTestId('trip-day-rise-set');
      if ((await riseSet.count()) > 0) {
        await expect(riseSet).toContainText(/일출 \d{2}:\d{2}/);
        await expect(riseSet).toContainText(/일몰 \d{2}:\d{2}/);
      } else if ((await header.getByTestId('trip-day-rise-set-pending').count()) > 0) {
        // origin/main b1cef056: 공유(readOnly) 화면은 pending_fetch→'준비 중', 그 외 pending→'정보 없음'.
        await expect(header.getByTestId('trip-day-rise-set-pending')).toHaveText(
          /^일출·일몰 (준비 중|정보 없음)$/,
        );
        // 편집 지시 문구("…추가하면…")는 읽기 전용 화면에 나오면 안 된다.
        await expect(header).not.toContainText('추가하면');
      }
      const asideText = (await aside.textContent()) ?? '';
      const headerText = (await header.textContent()) ?? '';
      expect(`${asideText}\n${headerText}`).not.toMatch(/undefined|NaN|\[object|null/);
      await shot(fresh.page, 'SHR-011', '01-weather-neutral');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-012 공유 페이지 일자 탭 전환 (transit: 서울역)', async ({ page, browser }) => {
    const title = uniqueTitle('012');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-21' });
    created.push(id);
    await gotoTrip(page, id, title);
    const day2Place = await searchAndAddPlace(page, 2, '서울역');
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      const tabs = fresh.page.getByRole('tablist', { name: '일자 선택' });
      await expect(tabs.getByRole('tab')).toHaveCount(2);
      await tabs.getByRole('tab', { name: /2일차/ }).click();
      await expect(tabs.getByRole('tab', { name: /2일차/ })).toHaveAttribute(
        'aria-selected',
        'true',
      );
      await expect(tabs.getByRole('tab', { name: /1일차/ })).toHaveAttribute(
        'aria-selected',
        'false',
      );
      await expect(fresh.page.getByTestId('trip-poi-list')).toContainText(day2Place);
      await tabs.getByRole('tab', { name: /1일차/ }).click();
      await expect(fresh.page.getByTestId('trip-poi-list')).not.toContainText(day2Place);
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-015 다른 여행 id + 토큰 조합/잘못된 토큰은 404', async ({ page, browser }) => {
    const titleA = uniqueTitle('015A');
    const titleB = uniqueTitle('015B');
    const a = await createTrip(page, { title: titleA, start: '2026-11-20', end: '2026-11-20' });
    created.push(a.id);
    const b = await createTrip(page, { title: titleB, start: '2026-11-20', end: '2026-11-20' });
    created.push(b.id);
    await gotoTrip(page, a.id, titleA);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    const swapped = await openSharedInFreshContext(browser, b.id, link.token);
    try {
      expect(swapped.apiStatus).toBe(404);
      await expectSharedError(swapped.page, '공유 토큰을 찾을 수 없습니다');
      await expect(swapped.page.getByText(titleB)).toHaveCount(0);
    } finally {
      await swapped.context.close();
    }
    const malformed = await openSharedInFreshContext(browser, a.id, 'not-a-real-token');
    try {
      expect(malformed.apiStatus).toBe(404);
      await expectSharedError(malformed.page, '공유 토큰을 찾을 수 없습니다');
    } finally {
      await malformed.context.close();
    }
  });

  test('SHR-016 삭제된 여행의 공유 링크는 "여행을 찾을 수 없습니다"', async ({ page, browser }) => {
    const title = uniqueTitle('016');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    const link = await createShareLink(page);

    // UI 삭제(soft delete): 삭제 → 삭제 확인 → 목록으로.
    await page.getByTestId('trip-actions').getByRole('button', { name: '삭제' }).click();
    await page.getByTestId('trip-delete-confirm').click();
    await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/);

    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(404);
      await expectSharedError(fresh.page, '여행을 찾을 수 없습니다');
      await expect(fresh.page.getByRole('heading', { level: 1, name: title })).toHaveCount(0);
      await shot(fresh.page, 'SHR-016', '01-deleted-trip-share');
    } finally {
      await fresh.context.close();
    }
  });

  test('SHR-035 권한별 링크 3개 — 목록 라벨과 활성 상태', async ({ page }) => {
    const title = uniqueTitle('035');
    const { id } = await createTrip(page, { title, start: '2026-11-20', end: '2026-11-20' });
    created.push(id);
    await gotoTrip(page, id, title);
    await openTripTab(page, '공유');
    await createShareLink(page, { visibility: 'view_only' });
    await createShareLink(page, { visibility: 'comment' });
    await createShareLink(page, { visibility: 'edit' });

    const list = page.getByTestId('share-link-list');
    await expect(list.getByRole('listitem')).toHaveCount(3);
    for (const label of ['보기 전용', '댓글 가능', '편집 가능']) {
      const item = list.getByRole('listitem').filter({ hasText: label });
      await expect(item).toHaveCount(1);
      await expect(item).toContainText('활성');
      await expect(item.getByRole('button', { name: '공유 링크 철회' })).toHaveCount(1);
    }
    // 권한 셀렉트의 옵션 집합도 고정값이다.
    await expect(shareSection(page).getByLabel('권한').locator('option')).toHaveText([
      '보기 전용',
      '댓글 가능',
      '편집 가능',
    ]);
    await shot(page, 'SHR-035', '01-three-links');
  });
});
