import { expect, test } from '@playwright/test';

const noticePlanId = '33333333-3333-4333-8333-333333333333';
const tripId = '11111111-1111-4111-8111-111111111111';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const PLAN = {
  notice_plan_id: noticePlanId,
  slug: 'seoul-weekend',
  title: '서울 추천 주말 코스',
  category: 'recommended',
  summary: '가볍게 걷고 쉬는 서울 주말 코스',
  source_name: 'Pinvi',
  destination: '서울',
  starts_on: '2026-06-20',
  ends_on: '2026-06-21',
  is_published: true,
  version: 1,
  created_at: '2026-06-01T09:00:00+09:00',
  updated_at: '2026-06-01T09:00:00+09:00',
  pois: [],
};

test('추천 여행을 새 여행으로 복사하면 결과 링크가 표시된다', async ({ page }) => {
  await page.route(/.*\/notice-plans(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: [PLAN] }),
    });
  });

  // 다이얼로그가 기존 여행 목록을 조회한다(빈 목록).
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  // 복사 POST → 새 여행 생성 결과.
  await page.route(/.*\/notice-plans\/[0-9a-f-]{36}\/copy$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip_id: tripId,
          created_trip: true,
          copied_poi_ids: [],
          copied_attachment_count: 0,
        },
      }),
    });
  });

  await page.goto('/notice-plans');

  await expect(page.getByTestId('notice-plan-list')).toContainText('서울 추천 주말 코스');
  await page.getByTestId(`notice-plan-copy-${noticePlanId}`).click();

  const dialog = page.getByTestId('notice-copy-dialog');
  await expect(dialog).toBeVisible();

  // Escape 로 닫힌다(키보드 접근성).
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();

  // 다시 열어 복사 진행.
  await page.getByTestId(`notice-plan-copy-${noticePlanId}`).click();
  await expect(dialog).toBeVisible();
  await page.getByTestId('notice-copy-confirm').click();

  await expect(dialog).toContainText('새 여행을 만들었습니다.');
  await expect(dialog.getByRole('link', { name: '여행 열기' })).toHaveAttribute(
    'href',
    `/trips/${tripId}`
  );
});
