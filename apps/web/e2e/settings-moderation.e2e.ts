import { expect, test, type Route } from '@playwright/test';

const reportId = '11111111-1111-4111-8111-111111111111';
const targetId = '22222222-2222-4222-8222-222222222222';

function reportRecord(overrides: Record<string, unknown> = {}) {
  return {
    report_id: reportId,
    target_type: 'trip',
    target_id: targetId,
    target_trip_id: targetId,
    target_owner_user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    reporter_user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    reason_code: 'privacy',
    reason_text: '개인정보 노출 신고',
    status: 'hidden',
    target_snapshot: { title: '여행' },
    evidence: {},
    reviewer_user_id: null,
    resolution_summary: '임시 숨김',
    appeal_summary: null,
    reviewed_at: null,
    actioned_at: '2026-06-28T09:00:00+09:00',
    appealed_at: null,
    restored_at: null,
    next_actions: ['restore'],
    actions: [],
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

test('사용자 신고/이의제기 설정 화면에서 접수와 appeal을 수행한다', async ({ page }) => {
  let rows = [reportRecord()];
  let createBody: Record<string, unknown> | null = null;
  let appealBody: Record<string, unknown> | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/users/me/content-reports',
    async (route, request) => {
      if (request.method() === 'POST') {
        createBody = request.postDataJSON() as Record<string, unknown>;
        rows = [
          reportRecord({
            status: 'received',
            target_type: String(createBody.target_type),
            target_id: String(createBody.target_id),
            reason_code: String(createBody.reason_code),
            reason_text: String(createBody.reason_text),
            resolution_summary: null,
            next_actions: ['review', 'hide', 'takedown', 'reject'],
          }),
          ...rows,
        ];
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

  await page.route(/.*\/users\/me\/content-reports\/[^/]+\/appeal$/, async (route) => {
    appealBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      reportRecord({
        status: 'appealed',
        appeal_summary: String(appealBody.appeal_reason),
        appealed_at: '2026-06-28T09:10:00+09:00',
        next_actions: ['restore', 'takedown', 'reject'],
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.goto('/settings/moderation');
  await expect(page.getByRole('heading', { name: '신고/이의제기' })).toBeVisible();
  await expect(page.getByTestId('settings-tab-moderation')).toBeVisible();

  await page.getByLabel('대상 ID').fill(targetId);
  await page.getByLabel('신고 내용').fill('여행 설명에 개인정보가 포함되어 있습니다.');
  await page.getByLabel('증빙 정보').fill('{"field":"description"}');
  await page.getByTestId('settings-moderation-submit').click();

  await expect(page.getByText(`${reportId} 신고를 접수했습니다.`)).toBeVisible();
  expect(createBody).toMatchObject({
    target_type: 'trip',
    target_id: targetId,
    reason_code: 'privacy',
    reason_text: '여행 설명에 개인정보가 포함되어 있습니다.',
    evidence: { field: 'description' },
  });

  await page
    .getByRole('button', { name: `${reportId} 신고 이의제기` })
    .first()
    .click();
  await page.getByLabel('이의제기 사유').fill('개인정보가 아닌 공개 별명입니다.');
  await page.getByTestId('settings-moderation-appeal-submit').click();

  await expect(page.getByText(`${reportId} 신고에 이의제기를 제출했습니다.`)).toBeVisible();
  expect(appealBody).toMatchObject({ appeal_reason: '개인정보가 아닌 공개 별명입니다.' });
});
