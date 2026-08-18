import { expect, test, type Page } from '@playwright/test';

/**
 * T-314 리뷰 회귀 방지 — 모바일 앱 셸(하단 탭바/더보기 시트)과 대시보드 오류 상태.
 * 각 항목은 적대적 리뷰가 실제로 재현한 실패 시나리오를 그대로 고정한다.
 */

const userId = '22222222-2222-4222-8222-222222222222';
const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function trip(index: number) {
  const id = `11111111-1111-4111-8111-1111111111${String(10 + index)}`;
  return {
    trip_id: id,
    owner_user_id: userId,
    title: `여행 ${index}`,
    description: null,
    region_hint: '서울',
    primary_region_code: '11',
    primary_region_source: 'manual',
    start_date: '2099-06-20',
    end_date: '2099-06-21',
    visibility: 'private',
    status: 'planned',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

async function mockTripList(page: Page, count: number, options: { postStatus?: number } = {}) {
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'POST') {
      await route.fulfill({
        status: options.postStatus ?? 201,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '여행을 저장하지 못했습니다.' }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: Array.from({ length: count }, (_, index) => trip(index + 1)),
      }),
    });
  });
  // 목록 지도 POI 조회는 비워 둔다(레이아웃 측정만 한다).
  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
  });
}

test.describe('모바일 앱 셸', () => {
  test.use({ viewport: { width: 768, height: 800 } });

  test('768px에서도 고정 하단 탭바가 목록 마지막 항목을 가리지 않는다', async ({ page }) => {
    await mockTripList(page, 12);
    await page.goto('/trips');
    await expect(page.getByTestId('trip-list')).toBeVisible();

    await page.mouse.wheel(0, 4000);
    await page.waitForTimeout(300);

    const navBox = await page.locator('nav[aria-label="주요 메뉴"]').boundingBox();
    const lastCard = page.getByTestId('trip-list').locator('a').last();
    await lastCard.scrollIntoViewIfNeeded();
    const cardBox = await lastCard.boundingBox();

    expect(navBox).not.toBeNull();
    expect(cardBox).not.toBeNull();
    // 마지막 카드 하단이 탭바 상단보다 위에 있어야 한다(가려지면 스크롤로도 드러나지 않는다).
    expect(cardBox!.y + cardBox!.height).toBeLessThanOrEqual(navBox!.y);
  });
});

test.describe('더보기 시트', () => {
  test.use({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });

  test('버튼 시맨틱을 노출하고 라우팅·바깥 클릭으로 닫힌다', async ({ page }) => {
    await mockTripList(page, 1);
    await page.route(/.*\/files(\?.*)?$/, async (route, request) => {
      if (!isFetch(request.resourceType())) return route.continue();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    });
    await page.goto('/trips');

    const toggle = page.getByRole('button', { name: /더보기/ });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const sheetLink = page.getByTestId('app-nav--profile-mobile');
    await expect(sheetLink).toBeVisible();

    // 바깥(본문) 클릭으로 닫힌다.
    await page.getByRole('heading', { name: '여행', exact: true }).click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');

    // 시트 안에서 이동하면 도착 페이지에서 시트가 열린 채 남지 않는다.
    await toggle.click();
    await page.getByTestId('app-nav--files-mobile').click();
    await expect(page).toHaveURL(/\/files$/);
    await expect(page.getByRole('button', { name: /더보기/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });
});

test.describe('넓은 layout viewport 폰', () => {
  test.use({
    viewport: { width: 1180, height: 915 },
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36',
  });

  test('lg 이상 폭이어도 모바일 셸(하단 탭바)을 쓴다', async ({ page }) => {
    await mockTripList(page, 1);
    await page.goto('/trips');
    await expect(page.getByTestId('trip-list')).toBeVisible();

    await expect(page.locator('nav[aria-label="주요 메뉴"]')).toBeVisible();
    await expect(page.locator('nav[aria-label="사용자 메뉴"]')).toBeHidden();
  });
});

test('여행 저장 실패는 목록을 지우지 않고 배너로만 알린다', async ({ page }) => {
  await mockTripList(page, 1, { postStatus: 500 });
  await page.goto('/trips');
  await expect(page.getByTestId('trip-list')).toContainText('여행 1');

  await page.getByTestId('trip-create-title').fill('저장 실패 확인');
  await page.getByTestId('trip-create-submit').click();

  await expect(page.getByTestId('trips-error')).toBeVisible();
  await expect(page.getByTestId('trip-list')).toContainText('여행 1');
  await expect(page.getByTestId('trip-list-error')).toHaveCount(0);
});

test('목록 로드 실패는 라이브 리전으로 알리고 회복 행동을 준다', async ({ page }) => {
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '여행 목록을 불러오지 못했습니다.' }),
    });
  });
  await page.goto('/trips');

  const panel = page.getByTestId('trip-list-error');
  await expect(panel).toBeVisible();
  await expect(panel).toHaveAttribute('role', 'alert');
  await expect(panel.getByRole('button', { name: '다시 시도' })).toBeVisible();
  await expect(page.getByTestId('trips-error')).toHaveCount(0);
});
