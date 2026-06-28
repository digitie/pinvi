import { expect, test, type Page, type Route } from '@playwright/test';

const adminUser = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'operator@example.com',
  nickname: 'Operator',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin', 'operator'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const reportId = '11111111-1111-4111-8111-111111111111';
const targetId = '22222222-2222-4222-8222-222222222222';

type ReportStatus =
  | 'received'
  | 'reviewing'
  | 'hidden'
  | 'taken_down'
  | 'rejected'
  | 'appealed'
  | 'restored';

function nextActions(status: ReportStatus) {
  if (status === 'received') return ['review', 'hide', 'takedown', 'reject'];
  if (status === 'reviewing') return ['hide', 'takedown', 'reject'];
  if (status === 'appealed') return ['restore', 'takedown', 'reject'];
  if (status === 'hidden' || status === 'taken_down') return ['restore'];
  return [];
}

function reportRecord(overrides: Record<string, unknown> = {}) {
  const status = (overrides.status as ReportStatus | undefined) ?? 'received';
  return {
    report_id: reportId,
    target_type: 'comment',
    target_id: targetId,
    target_trip_id: '33333333-3333-4333-8333-333333333333',
    target_owner_user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    reporter_user_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    reason_code: 'privacy',
    reason_text: '댓글에 개인정보가 포함되어 있습니다.',
    status,
    target_snapshot: { body: '개인정보 댓글' },
    evidence: { source: 'e2e' },
    reviewer_user_id: null,
    resolution_summary: null,
    appeal_summary: null,
    reviewed_at: null,
    actioned_at: null,
    appealed_at: null,
    restored_at: null,
    next_actions: nextActions(status),
    actions: [],
    created_at: '2026-06-28T09:00:00+09:00',
    updated_at: '2026-06-28T09:00:00+09:00',
    ...overrides,
  };
}

async function mockAdminAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: adminUser }),
    });
  });
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function continueIfWebRequest(route: Route) {
  const url = new URL(route.request().url());
  if (url.port !== '12801') {
    await route.continue();
    return true;
  }
  return false;
}

test('Admin Moderation page가 신고 목록과 조치 흐름을 렌더링한다', async ({ page }) => {
  await mockAdminAuth(page);
  const requests: string[] = [];
  let rows = [reportRecord()];
  let reviewBody: Record<string, unknown> | null = null;
  let hideBody: Record<string, unknown> | null = null;

  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/admin\/moderation\/reports\/[^/]+\/review$/, async (route) => {
    reviewBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      reportRecord({
        status: 'reviewing',
        reviewer_user_id: adminUser.user_id,
        resolution_summary: String(reviewBody.resolution_summary),
        reviewed_at: '2026-06-28T09:10:00+09:00',
        updated_at: '2026-06-28T09:10:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/moderation\/reports\/[^/]+\/hide$/, async (route) => {
    hideBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      reportRecord({
        status: 'hidden',
        reviewer_user_id: adminUser.user_id,
        resolution_summary: String(hideBody.resolution_summary),
        actioned_at: '2026-06-28T09:20:00+09:00',
        updated_at: '2026-06-28T09:20:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/moderation\/reports(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;

    await fulfillJson(route, {
      data: {
        items: rows,
        page_size: 100,
        total: rows.length,
      },
    });
  });

  await page.goto('/admin/moderation');

  await expect(page.getByRole('heading', { name: 'Moderation' })).toBeVisible();
  await expect(page.getByTestId('admin-nav--admin-moderation')).toBeVisible();
  await expect(page.getByTestId(`admin-moderation-row-${reportId}`)).toContainText(
    '댓글에 개인정보가 포함되어 있습니다.',
  );

  await page.getByTestId('admin-moderation-status-filter').selectOption('reviewing');
  await expect
    .poll(() =>
      requests.some(
        (url) => url.includes('/admin/moderation/reports') && url.includes('status=reviewing'),
      ),
    )
    .toBe(true);

  await page.getByTestId(`admin-moderation-action-review-${reportId}`).click();
  await page.getByLabel('처리 요약').fill('신고 내용 확인 시작');
  await page.getByLabel('접근 사유').fill('moderation queue triage');
  await page.getByTestId('admin-moderation-action-submit').click();

  await expect(page.getByText(`${reportId} 신고를 검토 시작 처리했습니다.`)).toBeVisible();
  expect(reviewBody).toMatchObject({
    access_reason: 'moderation queue triage',
    resolution_summary: '신고 내용 확인 시작',
  });

  await page.getByTestId(`admin-moderation-action-hide-${reportId}`).click();
  await page.getByLabel('처리 요약').fill('개인정보 포함 댓글 숨김');
  await page.getByLabel('접근 사유').fill('privacy report action');
  await page.getByTestId('admin-moderation-action-submit').click();

  await expect(page.getByText(`${reportId} 신고를 숨김 처리했습니다.`)).toBeVisible();
  expect(hideBody).toMatchObject({
    access_reason: 'privacy report action',
    resolution_summary: '개인정보 포함 댓글 숨김',
  });
});
