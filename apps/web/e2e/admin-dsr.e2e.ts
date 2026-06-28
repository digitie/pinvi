import { expect, test, type Page, type Route } from '@playwright/test';

const cpoUser = {
  user_id: '99999999-9999-4999-8999-999999999999',
  email: 'cpo@example.com',
  nickname: 'CPO',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin', 'cpo'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const requestId = '11111111-1111-4111-8111-111111111111';

type DsrStatus =
  | 'received'
  | 'identity_check'
  | 'processing'
  | 'completed'
  | 'rejected'
  | 'withdrawn';

function dsrRecord(overrides: Record<string, unknown> = {}) {
  const status = (overrides.status as DsrStatus | undefined) ?? 'received';
  return {
    request_id: requestId,
    user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    request_type: 'access',
    status,
    request_summary: '최근 1년 위치/계정 정보 열람 요청',
    request_details: { scope: 'profile_location' },
    identity_proof_metadata: { method: 'authenticated_session', verified: false },
    requester_email_masked: 'u***@pinvi.test',
    assigned_cpo_user_id: null,
    received_at: '2026-06-28T09:00:00+09:00',
    due_at: '2026-07-08T09:00:00+09:00',
    identity_verified_at: null,
    processing_started_at: null,
    completed_at: null,
    rejected_at: null,
    withdrawn_at: null,
    rejection_reason: null,
    result_summary: null,
    result_notice_hash: null,
    result_notice_email_id: null,
    export_manifest: {},
    partial_response: false,
    evidence_attachment_id: null,
    response_overdue: false,
    next_action: status === 'received' ? 'identity_check' : 'process',
    created_at: '2026-06-28T09:00:00+09:00',
    updated_at: '2026-06-28T09:00:00+09:00',
    ...overrides,
  };
}

async function mockCpoAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: cpoUser }),
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

test('Admin DSR page가 목록, 필터, CPO 처리 흐름을 렌더링한다', async ({ page }) => {
  await mockCpoAuth(page);
  const requests: string[] = [];
  let rows = [dsrRecord()];
  let identityBody: Record<string, unknown> | null = null;
  let processBody: Record<string, unknown> | null = null;
  let completeBody: Record<string, unknown> | null = null;

  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/admin\/dsr\/[^/]+\/identity-check$/, async (route) => {
    identityBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      dsrRecord({
        status: 'identity_check',
        assigned_cpo_user_id: cpoUser.user_id,
        identity_verified_at: '2026-06-28T09:10:00+09:00',
        identity_proof_metadata: { verified: true },
        next_action: 'process',
        updated_at: '2026-06-28T09:10:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/dsr\/[^/]+\/process$/, async (route) => {
    processBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      dsrRecord({
        status: 'processing',
        assigned_cpo_user_id: cpoUser.user_id,
        identity_verified_at: '2026-06-28T09:10:00+09:00',
        processing_started_at: '2026-06-28T09:20:00+09:00',
        next_action: 'complete_or_reject',
        updated_at: '2026-06-28T09:20:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/dsr\/[^/]+\/complete$/, async (route) => {
    completeBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      dsrRecord({
        status: 'completed',
        assigned_cpo_user_id: cpoUser.user_id,
        result_summary: String(completeBody.result_summary),
        result_notice_hash: 'abc123',
        export_manifest: completeBody.export_manifest,
        partial_response: completeBody.partial_response,
        completed_at: '2026-06-28T09:30:00+09:00',
        next_action: 'none',
        updated_at: '2026-06-28T09:30:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/dsr(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;

    await fulfillJson(route, {
      data: {
        items: rows,
        page_size: 100,
        total: rows.length,
      },
    });
  });

  await page.goto('/admin/dsr');

  await expect(page.getByRole('heading', { name: 'DSR' })).toBeVisible();
  await expect(page.getByTestId('admin-nav--admin-dsr')).toBeVisible();
  await expect(page.getByTestId(`admin-dsr-row-${requestId}`)).toContainText(
    '최근 1년 위치/계정 정보 열람 요청',
  );

  await page.getByTestId('admin-dsr-status-filter').selectOption('processing');
  await expect
    .poll(() =>
      requests.some((url) => url.includes('/admin/dsr') && url.includes('status=processing')),
    )
    .toBe(true);

  await page.getByTestId(`admin-dsr-action-identity_check-${requestId}`).click();
  await page.getByLabel('확인 메모').fill('로그인 세션과 계정 이메일 일치');
  await page.getByRole('textbox', { name: '사유' }).fill('본인 확인 처리');
  await page.getByTestId('admin-dsr-action-submit').click();

  await expect(page.getByText(`${requestId} DSR 요청을 본인 확인 처리했습니다.`)).toBeVisible();
  expect(identityBody).toMatchObject({
    access_reason: '본인 확인 처리',
    identity_verified: true,
    identity_note: '로그인 세션과 계정 이메일 일치',
  });

  await page.getByTestId(`admin-dsr-action-process-${requestId}`).click();
  await page.getByLabel('처리 메모').fill('열람 자료 추출 시작');
  await page.getByRole('textbox', { name: '사유' }).fill('CPO 처리 시작');
  await page.getByTestId('admin-dsr-action-submit').click();

  await expect(page.getByText(`${requestId} DSR 요청을 처리 시작 처리했습니다.`)).toBeVisible();
  expect(processBody).toMatchObject({
    access_reason: 'CPO 처리 시작',
    processing_note: '열람 자료 추출 시작',
  });

  await page.getByTestId(`admin-dsr-action-complete-${requestId}`).click();
  await page.getByLabel('결과 요약').fill('프로필과 위치 접근 로그 export를 제공했습니다.');
  await page
    .getByLabel('Export manifest')
    .fill('{"files":["profile.json"],"masked_fields":["email"]}');
  await page.getByLabel('부분 제공').check();
  await page.getByRole('textbox', { name: '사유' }).fill('결과 통지 완료');
  await page.getByTestId('admin-dsr-action-submit').click();

  await expect(page.getByText(`${requestId} DSR 요청을 완료 처리했습니다.`)).toBeVisible();
  expect(completeBody).toMatchObject({
    access_reason: '결과 통지 완료',
    result_summary: '프로필과 위치 접근 로그 export를 제공했습니다.',
    export_manifest: { files: ['profile.json'], masked_fields: ['email'] },
    partial_response: true,
  });
});
