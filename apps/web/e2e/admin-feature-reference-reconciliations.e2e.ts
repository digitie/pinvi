import { expect, test, type Page } from '@playwright/test';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-08-21T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const appliedEventId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const blockedEventId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const appliedAttempt = {
  event_id: appliedEventId,
  attempt_sequence: 1,
  event_sequence: 10,
  event_sha256: 'a'.repeat(64),
  status: 'applied',
  block_fingerprint_sha256: null,
  observation_root_sha256: 'b'.repeat(64),
  observed_at: '2026-08-21T10:00:00+09:00',
};
const blockedAttempt = {
  event_id: blockedEventId,
  attempt_sequence: 2,
  event_sequence: 11,
  event_sha256: 'c'.repeat(64),
  status: 'blocked',
  block_fingerprint_sha256: 'd'.repeat(64),
  observation_root_sha256: 'e'.repeat(64),
  observed_at: '2026-08-21T10:01:00+09:00',
};
const receipt = {
  event_id: appliedEventId,
  event_sequence: 10,
  event_sha256: 'a'.repeat(64),
  action: 'rebind',
  old_feature_id: 'feature-old',
  old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  replacement_feature_id: 'feature-new',
  replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  impact_root_sha256: 'f'.repeat(64),
  impact_count: 3,
  receipt_sha256: '0'.repeat(64),
  applied_at: '2026-08-21T10:00:00+09:00',
};

async function expectNoRootHorizontalScroll(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => ({
        body: document.body.scrollWidth <= document.body.clientWidth + 1,
        html: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
      })),
    )
    .toEqual({ body: true, html: true });
}

async function expectTouchTarget(page: Page, testId: string) {
  const box = await page.getByTestId(testId).boundingBox();
  expect(box, `${testId} bounding box`).not.toBeNull();
  expect(Math.round(box!.width), `${testId} width`).toBeGreaterThanOrEqual(44);
  expect(Math.round(box!.height), `${testId} height`).toBeGreaterThanOrEqual(44);
}

async function expectInInitialViewport(page: Page, testId: string) {
  await expect(page.getByTestId(testId)).toBeInViewport({ ratio: 1 });
}

function isBlockedDetailRoute(url: URL) {
  return (
    url.port === '12801' &&
    url.pathname === `/admin/feature-reference-reconciliations/${blockedEventId}`
  );
}

async function routeBlockedDetail(
  page: Page,
  { failuresBeforeSuccess = 0 }: { failuresBeforeSuccess?: number } = {},
) {
  let calls = 0;
  await page.route(isBlockedDetailRoute, async (route) => {
    calls += 1;
    if (calls <= failuresBeforeSuccess) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'TEST_ERROR', message: 'temporary failure' } }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          event_id: blockedEventId,
          status: 'blocked',
          receipt: null,
          attempts: [blockedAttempt],
          impacts: [],
        },
      }),
    });
  });
  return { calls: () => calls };
}

async function closeDetailDialog(page: Page) {
  await page.getByTestId('admin-frr-detail-dialog-close').click();
  await expect(page.getByRole('dialog', { name: 'Feature 참조 조정 증거 상세' })).toBeHidden();
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
    (url) => url.port === '12801' && url.pathname === '/admin/feature-reference-reconciliations',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [
              {
                event_id: appliedEventId,
                status: 'applied',
                event_sequence: 10,
                event_sha256: 'a'.repeat(64),
                observed_at: '2026-08-21T10:00:00+09:00',
                receipt,
                latest_attempt: appliedAttempt,
              },
              {
                event_id: blockedEventId,
                status: 'blocked',
                event_sequence: 11,
                event_sha256: 'c'.repeat(64),
                observed_at: '2026-08-21T10:01:00+09:00',
                receipt: null,
                latest_attempt: blockedAttempt,
              },
            ],
            total: 2,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/feature-reference-reconciliations/${appliedEventId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            event_id: appliedEventId,
            status: 'applied',
            receipt,
            attempts: [appliedAttempt],
            impacts: [
              {
                event_id: appliedEventId,
                impact_index: 0,
                target_relation: 'trip_day_pois',
                target_id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
                old_feature_id: 'feature-old',
                old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                replacement_feature_id: 'feature-new',
                replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
                outcome: 'rebind',
                recorded_at: '2026-08-21T10:00:00+09:00',
              },
              {
                event_id: appliedEventId,
                impact_index: 1,
                target_relation: 'curated_plan_pois',
                target_id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
                old_feature_id: 'feature-old',
                old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                replacement_feature_id: null,
                replacement_feature_uuid: null,
                outcome: 'detach',
                recorded_at: '2026-08-21T10:00:01+09:00',
              },
              {
                event_id: appliedEventId,
                impact_index: 2,
                target_relation: 'feature_suggestions',
                target_id: '99999999-9999-4999-8999-999999999999',
                old_feature_id: 'feature-old',
                old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
                replacement_feature_id: 'feature-new',
                replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
                outcome: 'already_reconciled',
                recorded_at: '2026-08-21T10:00:02+09:00',
              },
            ],
          },
        }),
      });
    },
  );
});

test('Admin이 M05 receipt와 blocked evidence를 Dialog에서 읽기 전용으로 확인한다', async ({
  page,
}) => {
  await routeBlockedDetail(page);

  const evidenceRequests: string[] = [];
  const mutationRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      url.port === '12801' &&
      url.pathname.startsWith('/admin/feature-reference-reconciliations')
    ) {
      evidenceRequests.push(`${request.method()} ${url.pathname}`);
      if (request.method() !== 'GET') mutationRequests.push(`${request.method()} ${url.pathname}`);
    }
  });
  await page.goto('/admin/feature-reference-reconciliations');

  await expect(page.getByRole('heading', { name: 'Feature 참조 조정 증거' })).toBeVisible();
  await expect(
    page.getByTestId(`admin-frr-row-${blockedEventId}`).getByText('차단됨'),
  ).toBeVisible();
  await page.getByTestId(`admin-frr-detail-${blockedEventId}`).click();

  const dialog = page.getByRole('dialog', { name: 'Feature 참조 조정 증거 상세' });
  await expect(dialog).toBeVisible();
  const blockedDetail = page.getByTestId('admin-frr-detail');
  await expect(page.getByTestId('admin-frr-readonly-boundary')).toContainText('읽기 전용');
  await expect(page.getByTestId('admin-frr-readonly-boundary')).toBeFocused();
  await expect(blockedDetail).toContainText(
    '차단(blocked) 관측으로 local mutation과 Map ACK를 중단했습니다.',
  );
  await expect(blockedDetail).toContainText('차단 fingerprint SHA-256');
  await expect(blockedDetail).toContainText('관측 root SHA-256');
  await expect(blockedDetail).toContainText(blockedAttempt.event_sha256);
  await expect(blockedDetail).toContainText(blockedAttempt.block_fingerprint_sha256);
  await expect(blockedDetail).toContainText(blockedAttempt.observation_root_sha256);
  await closeDetailDialog(page);
  await page.getByTestId(`admin-frr-detail-${appliedEventId}`).click();

  const detail = page.getByTestId('admin-frr-detail');
  await expect(detail).toContainText('반영 완료');
  await expect(detail).toContainText('Event SHA-256');
  await expect(detail).toContainText('이전 Feature UUID');
  await expect(detail).toContainText('대체 Feature UUID');
  await expect(detail).toContainText('영향 root SHA-256');
  await expect(detail).toContainText('적용 시각');
  await expect(detail).toContainText(receipt.event_sha256);
  await expect(detail).toContainText(receipt.old_feature_uuid);
  await expect(detail).toContainText(receipt.replacement_feature_uuid);
  await expect(detail).toContainText(receipt.impact_root_sha256);
  await expect(detail).toContainText(receipt.receipt_sha256);
  await expect(detail).toContainText('여행 일정 POI');
  await expect(detail).toContainText('큐레이션 POI');
  await expect(detail).toContainText('Feature 제안');
  await expect(detail).toContainText('trip_day_pois');
  await expect(detail).toContainText('curated_plan_pois');
  await expect(detail).toContainText('feature_suggestions');
  await expect(detail).toContainText('대체 Feature로 재연결');
  await expect(detail).toContainText('참조 분리');
  await expect(detail).toContainText('이미 조정됨');
  await expect(detail).toContainText('recorded_at');
  await expect(detail.getByRole('button', { name: '승인' })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '거절' })).toHaveCount(0);
  expect(mutationRequests).toEqual([]);
  expect(evidenceRequests).toEqual([
    'GET /admin/feature-reference-reconciliations',
    `GET /admin/feature-reference-reconciliations/${blockedEventId}`,
    `GET /admin/feature-reference-reconciliations/${appliedEventId}`,
  ]);
});

test('상세 Dialog는 키보드로 열리고 닫힌 뒤 trigger에 focus를 복원한다', async ({ page }) => {
  await routeBlockedDetail(page);
  await page.goto('/admin/feature-reference-reconciliations');

  const trigger = page.getByTestId(`admin-frr-detail-${blockedEventId}`);
  await trigger.focus();
  await page.keyboard.press('Enter');

  const dialog = page.getByRole('dialog', { name: 'Feature 참조 조정 증거 상세' });
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId('admin-frr-readonly-boundary')).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('상세 조회 실패는 Dialog 안에서 다시 시도할 수 있다', async ({ page }) => {
  const blockedDetail = await routeBlockedDetail(page, { failuresBeforeSuccess: 1 });

  await page.goto('/admin/feature-reference-reconciliations');
  await page.getByTestId(`admin-frr-detail-${blockedEventId}`).click();
  await expect(page.getByTestId('admin-frr-detail-retry')).toBeVisible();

  await page.getByTestId('admin-frr-detail-retry').click();

  await expect(page.getByTestId('admin-frr-readonly-boundary')).toContainText('읽기 전용');
  expect(blockedDetail.calls()).toBe(2);
});

test('데스크톱과 모바일 trigger는 중복 렌더 중 보이는 버튼만 열고 focus를 복원한다', async ({
  page,
}) => {
  await routeBlockedDetail(page);
  await page.setViewportSize({ width: 768, height: 820 });
  await page.goto('/admin/feature-reference-reconciliations');

  const desktopTrigger = page.getByTestId(`admin-frr-detail-${blockedEventId}`);
  const mobileTrigger = page.getByTestId(`admin-frr-mobile-detail-${blockedEventId}`);
  await expect(desktopTrigger).toBeVisible();
  await expect(mobileTrigger).toBeHidden();
  await expect(desktopTrigger).toHaveAttribute('aria-label', '이벤트 #11 조정 증거 보기');
  await desktopTrigger.click();
  await expect(page.getByTestId('admin-frr-readonly-boundary')).toBeFocused();
  await closeDetailDialog(page);
  await expect(desktopTrigger).toBeFocused();

  await page.setViewportSize({ width: 375, height: 820 });
  await expect(desktopTrigger).toBeHidden();
  await expect(mobileTrigger).toBeVisible();
  await expect(mobileTrigger).toHaveAttribute('aria-label', '이벤트 #11 조정 증거 보기');
  await mobileTrigger.click();
  await expect(page.getByTestId('admin-frr-readonly-boundary')).toBeFocused();
  await closeDetailDialog(page);
  await expect(mobileTrigger).toBeFocused();
});

for (const width of [320, 375, 414, 768]) {
  test(`M05 증거 화면은 ${width}px에서 root overflow 없이 읽기 전용 상세를 연다`, async ({
    page,
  }) => {
    await routeBlockedDetail(page);
    await page.setViewportSize({ width, height: 820 });
    await page.goto('/admin/feature-reference-reconciliations');

    await expectNoRootHorizontalScroll(page);
    await expectTouchTarget(page, 'admin-frr-status-filter');
    await expectTouchTarget(page, 'admin-frr-prev-page');
    await expectTouchTarget(page, 'admin-frr-next-page');

    if (width < 768) {
      await expect(page.getByTestId(`admin-frr-mobile-card-${blockedEventId}`)).toBeVisible();
      await expect(page.getByTestId(`admin-frr-detail-${blockedEventId}`)).toBeHidden();
      await expectTouchTarget(page, `admin-frr-mobile-detail-${blockedEventId}`);
      await expectInInitialViewport(page, `admin-frr-mobile-detail-${blockedEventId}`);
      await page.getByTestId(`admin-frr-mobile-detail-${blockedEventId}`).click();
    } else {
      await expect(page.getByTestId('admin-table-scroll')).toBeVisible();
      await expect(page.getByTestId(`admin-frr-mobile-detail-${blockedEventId}`)).toBeHidden();
      await expectTouchTarget(page, `admin-frr-detail-${blockedEventId}`);
      await page.getByTestId(`admin-frr-detail-${blockedEventId}`).click();
    }

    const dialog = page.getByRole('dialog', { name: 'Feature 참조 조정 증거 상세' });
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId('admin-frr-readonly-boundary')).toContainText('읽기 전용');
    await expect(dialog.getByRole('button', { name: '승인' })).toHaveCount(0);
    await expect(dialog.getByRole('button', { name: '거절' })).toHaveCount(0);
    await expectNoRootHorizontalScroll(page);
  });
}
