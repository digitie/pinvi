import { expect, test, type Route } from '@playwright/test';

const requestId = '11111111-1111-4111-8111-111111111111';

function dsrRecord(overrides: Record<string, unknown> = {}) {
  return {
    request_id: requestId,
    user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    request_type: 'access',
    status: 'received',
    request_summary: '프로필 열람 요청',
    request_details: { scope: 'profile' },
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
    next_action: 'identity_check',
    created_at: '2026-06-28T09:00:00+09:00',
    updated_at: '2026-06-28T09:00:00+09:00',
    ...overrides,
  };
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test('사용자 DSR 설정 화면에서 접수와 철회를 수행한다', async ({ page }) => {
  let rows = [dsrRecord()];
  let createBody: Record<string, unknown> | null = null;
  let withdrawBody: Record<string, unknown> | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/dsr-requests',
    async (route, request) => {
      if (request.method() === 'POST') {
        createBody = request.postDataJSON() as Record<string, unknown>;
        rows = [dsrRecord({ request_summary: String(createBody.request_summary) }), ...rows];
        await fulfillJson(route, { data: rows[0] }, 201);
        return;
      }
      await fulfillJson(route, {
        data: {
          items: rows,
          page_size: 100,
          total: rows.length,
        },
      });
    },
  );

  await page.route(/.*\/users\/me\/dsr-requests\/[^/]+\/withdraw$/, async (route) => {
    withdrawBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      dsrRecord({
        status: 'withdrawn',
        withdrawn_at: '2026-06-28T09:10:00+09:00',
        next_action: 'none',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.goto('/settings/dsr');
  await expect(page.getByRole('heading', { name: '개인정보 요청' })).toBeVisible();
  await expect(page.getByTestId('settings-tab-dsr')).toBeVisible();
  await expect(page.getByLabel('유형')).toBeVisible();
  await expect(page.getByLabel('요약')).toBeVisible();
  await expect(page.getByLabel('상세 내용')).toBeVisible();

  await page.getByLabel('요약').fill('최근 위치 접근 로그 열람');
  await page.getByLabel('상세 내용').fill('{"scope":"location_audit"}');
  await page.getByTestId('settings-dsr-submit').click();

  await expect(page.getByText(`${requestId} 요청을 접수했습니다.`)).toBeVisible();
  expect(createBody).toMatchObject({
    request_type: 'access',
    request_summary: '최근 위치 접근 로그 열람',
    request_details: { scope: 'location_audit' },
  });

  await page
    .getByRole('button', { name: `${requestId} 요청 철회` })
    .first()
    .click();
  await expect(page.getByText(`${requestId} 요청을 철회했습니다.`)).toBeVisible();
  expect(withdrawBody).toMatchObject({ reason: '사용자 self-service 철회' });
});
