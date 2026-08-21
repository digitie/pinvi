import { expect, test, type Locator, type Page } from '@playwright/test';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const requestId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const summary = {
  request_id: requestId,
  requester_user_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  requester_email_masked:
    'really-long-feature-request-reviewer-email-mask***@example-travel-domain.test',
  type: 'new_place',
  kind: 'place',
  name: '새 카페',
  coord: { lon: 129.0, lat: 35.0 },
  categories: ['카페'],
  note: '좋은 곳',
  target_feature_id: null,
  status: 'pending',
  kor_travel_map_ref: null,
  reviewed_by_admin_id: null,
  created_at: '2026-06-11T10:00:00+09:00',
  resolved_at: null,
};

const correctionRequestId = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const correctionSummary = {
  ...summary,
  request_id: correctionRequestId,
  type: 'correction',
  target_feature_id: '01900000-0000-7000-8000-000000000001',
  name: '수정 전 장소',
};

const mappedRequestId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const mappedSummary = {
  ...summary,
  request_id: mappedRequestId,
  name: 'Map 큐 전달 장소',
  status: 'approved',
  kor_travel_map_ref: {
    request_id: '01900000-0000-7000-8000-000000000009',
    state: 'pending',
    review_mode: 'feature_request_queue',
    action: 'submit',
  },
  reviewed_by_admin_id: adminUser.user_id,
  resolved_at: '2026-06-11T10:05:00+09:00',
};

async function expectNoRootHorizontalScroll(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => {
        const initialX = window.scrollX;
        const initialY = window.scrollY;
        window.scrollTo(1, initialY);
        const rootScrollable = window.scrollX > 0;
        window.scrollTo(initialX, initialY);
        return { rootScrollable };
      }),
    )
    .toEqual({ rootScrollable: false });
}

async function expectTouchTarget(locator: Locator, label: string) {
  const box = await locator.boundingBox();
  expect(box, `${label} bounding box`).not.toBeNull();
  expect(Math.round(box!.width), `${label} width`).toBeGreaterThanOrEqual(44);
  expect(Math.round(box!.height), `${label} height`).toBeGreaterThanOrEqual(44);
}

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/feature-requests',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [summary, correctionSummary, mappedSummary],
            total: 3,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );
});

test('Admin이 신규 장소를 승인하면 저장된 payload를 Map 요청 큐에 제출한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/feature-requests/${requestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'approved',
            kor_travel_map_ref: {
              request_id: requestId,
              state: 'pending',
              review_mode: 'feature_request_queue',
              action: 'submit',
            },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');
  await expect(page.getByRole('heading', { name: 'Feature 제안 검토' })).toBeVisible();
  await expect(
    page
      .getByTestId(`admin-fr-row-${requestId}`)
      .getByRole('cell', { name: '새 카페', exact: true }),
  ).toBeVisible();

  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await expect(page.getByTestId('admin-fr-review-dialog')).toBeVisible();
  await expect(page.getByTestId('admin-fr-review-panel')).toBeVisible();
  await expect(page.getByTestId('admin-fr-reason')).toBeFocused();

  await expect(page.getByTestId('admin-fr-queue-payload-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-category')).toHaveCount(0);
  await expect(page.getByTestId('admin-fr-marker-color')).toHaveCount(0);
  await expect(page.getByTestId('admin-fr-marker-icon')).toHaveCount(0);
  await page.getByTestId('admin-fr-reason').fill('실재 확인 완료');
  await page.getByTestId('admin-fr-approve').click();

  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-notice')).toBeFocused();
  expect(approveBody).toEqual({ access_reason: '실재 확인 완료' });
});

test('신규 장소는 카테고리/마커 없이도 저장된 요청을 제출할 수 있다', async ({ page }) => {
  await page.route(
    (url) =>
      url.port === '12801' && url.pathname === `/admin/feature-requests/${requestId}/approve`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'approved',
            kor_travel_map_ref: { request_id: requestId, state: 'pending' },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );
  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await page.getByTestId('admin-fr-reason').fill('사유만 입력');
  await page.getByTestId('admin-fr-approve').click();
  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-notice')).toBeFocused();
});

test('Admin이 정보 수정 승인에 명시한 변경 필드를 전달한다', async ({ page }) => {
  let approveBody: Record<string, unknown> | null = null;
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/feature-requests/${correctionRequestId}/approve`,
    async (route) => {
      approveBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: correctionRequestId,
            status: 'added',
            kor_travel_map_ref: { feature_id: '01900000-0000-7000-8000-000000000001' },
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${correctionRequestId}`).click();
  await page.getByTestId('admin-fr-name').fill('수정 후 장소');
  await page.getByTestId('admin-fr-category').fill('01070100');
  await page.getByTestId('admin-fr-reason').fill('현장 재확인');
  await page.getByTestId('admin-fr-approve').click();

  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-notice')).toBeFocused();
  expect(approveBody).toMatchObject({
    access_reason: '현장 재확인',
    name: '수정 후 장소',
    category: '01070100',
  });
});

test('거절은 확인 단계를 거친 뒤 사유만 전달한다', async ({ page }) => {
  let rejectBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/feature-requests/${requestId}/reject`,
    async (route) => {
      rejectBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            request_id: requestId,
            status: 'rejected',
            kor_travel_map_ref: null,
            reviewed_by_admin_id: adminUser.user_id,
            resolved_at: '2026-06-11T10:05:00+09:00',
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${requestId}`).click();
  await page.getByTestId('admin-fr-reason').fill('중복 제보');
  const rejectButton = page.getByTestId('admin-fr-reject');
  await rejectButton.click();

  await expect(page.getByTestId('admin-fr-reject-confirm')).toBeVisible();
  await expect(page.getByTestId('admin-fr-reject-confirmation')).toBeVisible();
  await expect(page.getByTestId('admin-fr-reject-reason-preview')).toContainText('중복 제보');
  await expect(page.getByTestId('admin-fr-reject-confirm-cancel')).toBeFocused();
  expect(rejectBody).toBeNull();

  await page.getByTestId('admin-fr-reject-confirm-cancel').click();
  await expect(rejectButton).toBeFocused();

  await rejectButton.click();
  await page.getByTestId('admin-fr-reject-confirm-confirm').click();
  await expect(page.getByTestId('admin-fr-notice')).toBeVisible();
  await expect(page.getByTestId('admin-fr-notice')).toBeFocused();
  expect(rejectBody).toEqual({ access_reason: '중복 제보' });
});

test('검토 dialog를 breakpoint 변경 뒤 닫아도 보이는 검토 버튼으로 포커스를 되돌린다', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 820 });
  await page.goto('/admin/feature-requests');
  const desktopTrigger = page.getByTestId(`admin-fr-review-${requestId}`);
  const mobileTrigger = page.getByTestId(`admin-fr-mobile-review-${requestId}`);
  await desktopTrigger.click();
  await expect(page.getByTestId('admin-fr-reason')).toBeFocused();

  await page.setViewportSize({ width: 375, height: 820 });
  await expect(desktopTrigger).toBeHidden();
  await expect(mobileTrigger).toBeVisible();
  await page.getByTestId('admin-fr-review-dialog-close').click();

  await expect(mobileTrigger).toBeFocused();
});

test('Map 전달 참조를 구조화해 보여준다', async ({ page }) => {
  await page.goto('/admin/feature-requests');
  await page.getByTestId(`admin-fr-review-${mappedRequestId}`).click();

  const mapRef = page.getByTestId('admin-fr-kor_travel_map-ref');
  await expect(mapRef).toContainText('Map 전달 상태');
  await expect(mapRef).toContainText('요청 ID');
  await expect(mapRef).toContainText('Map Feature 요청 큐 ID');
  await expect(mapRef).toContainText('01900000-0000-7000-8000-000000000009');
  const jsonSummary = page.getByTestId('admin-fr-map-ref-json-summary');
  await expectTouchTarget(jsonSummary, 'JSON summary');
  await jsonSummary.focus();
  await expect(jsonSummary).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(mapRef.locator('pre')).toBeVisible();
});

test('목록 오류는 복구 버튼으로 다시 조회할 수 있다', async ({ page }) => {
  let failList = true;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/feature-requests',
    async (route) => {
      if (failList) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: '일시 오류' }),
        });
        return;
      }

      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [summary],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/feature-requests');

  await expect(page.getByTestId('admin-fr-error')).toBeVisible();
  await expectTouchTarget(page.getByTestId('admin-fr-retry'), 'retry');
  failList = false;
  await page.getByTestId('admin-fr-retry').click();

  await expect(
    page
      .getByTestId(`admin-fr-row-${requestId}`)
      .getByRole('cell', { name: '새 카페', exact: true }),
  ).toBeVisible();
});

for (const width of [320, 375, 414, 768]) {
  test(`Feature 제안 검토 화면은 ${width}px에서 overflow 없이 44px 검토 타깃을 유지한다`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 820 });
    await page.goto('/admin/feature-requests');

    await expectNoRootHorizontalScroll(page);
    await expectTouchTarget(page.getByTestId('admin-fr-status-filter'), 'status filter');
    await expectTouchTarget(page.getByTestId('admin-fr-prev-page'), 'previous page');
    await expectTouchTarget(page.getByTestId('admin-fr-next-page'), 'next page');

    const trigger =
      width < 768
        ? page.getByTestId(`admin-fr-mobile-review-${requestId}`)
        : page.getByTestId(`admin-fr-review-${requestId}`);

    if (width < 768) {
      await expect(page.getByTestId('admin-mobile-cards')).toBeVisible();
      await expect(page.getByTestId(`admin-fr-mobile-card-${requestId}`)).toContainText(
        'really-long-feature-request-reviewer-email-mask',
      );
    } else {
      await expect(page.getByTestId('admin-table-scroll')).toBeVisible();
      await trigger.scrollIntoViewIfNeeded();
    }

    await expect(trigger).toHaveAttribute('aria-haspopup', 'dialog');
    await expect(trigger).toHaveAttribute('aria-label', '새 카페 신규 장소 제안 검토 열기');
    await expectTouchTarget(trigger, 'review trigger');
    if (width < 768) {
      await expect(trigger).toBeInViewport({ ratio: 1 });
    }
    await trigger.click();

    await expect(page.getByTestId('admin-fr-review-dialog')).toBeVisible();
    await expect(page.getByTestId('admin-fr-reason')).toBeFocused();
    await expectNoRootHorizontalScroll(page);

    await page.getByTestId('admin-fr-review-dialog-close').click();
    await expect(trigger).toBeFocused();
    await expectNoRootHorizontalScroll(page);
  });
}
