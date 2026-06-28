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

const incidentId = '11111111-1111-4111-8111-111111111111';
const createdIncidentId = '22222222-2222-4222-8222-222222222222';

type IncidentStatus = 'detected' | 'triage' | 'notification_decision' | 'reported' | 'closed';

function incidentRecord(overrides: Record<string, unknown> = {}) {
  const status = (overrides.status as IncidentStatus | undefined) ?? 'detected';
  return {
    incident_id: incidentId,
    incident_type: 'admin_export_anomaly',
    severity: 'high',
    status,
    source: 'admin_audit_log',
    summary: 'Admin bulk export anomaly',
    details: {},
    affected_user_count: 24,
    notification_required: false,
    assigned_cpo_user_id: null,
    request_id: null,
    detected_at: '2026-06-28T09:00:00+09:00',
    cpo_review_due_at: '2026-06-28T09:30:00+09:00',
    external_report_due_at: '2026-07-01T09:00:00+09:00',
    cpo_notified_at: '2026-06-28T09:01:00+09:00',
    acknowledged_at: status === 'detected' ? null : '2026-06-28T09:10:00+09:00',
    notification_decision_at: null,
    notified_at: null,
    kisa_reported_at: null,
    resolved_at: null,
    notification_payload_hash: null,
    external_report_receipt_ref: null,
    evidence_attachment_id: null,
    cpo_review_overdue: false,
    external_report_overdue: false,
    next_action: status === 'detected' ? 'triage' : 'notification_decision',
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

test('Admin incidents page가 목록, 필터, 등록, triage 조치를 렌더링한다', async ({ page }) => {
  await mockCpoAuth(page);
  const requests: string[] = [];
  let rows = [incidentRecord()];
  let triageBody: Record<string, unknown> | null = null;
  let createBody: Record<string, unknown> | null = null;

  page.on('request', (request) => requests.push(request.url()));

  await page.route(/.*\/admin\/incidents\/[^/]+\/triage$/, async (route) => {
    const url = new URL(route.request().url());
    const triagedIncidentId = decodeURIComponent(url.pathname.split('/').at(-2) ?? incidentId);
    triageBody = route.request().postDataJSON() as Record<string, unknown>;
    rows = [
      incidentRecord({
        incident_id: triagedIncidentId,
        status: 'triage',
        updated_at: '2026-06-28T09:10:00+09:00',
      }),
    ];
    await fulfillJson(route, { data: rows[0] });
  });

  await page.route(/.*\/admin\/incidents(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;

    if (route.request().method() === 'POST') {
      createBody = route.request().postDataJSON() as Record<string, unknown>;
      const created = incidentRecord({
        incident_id: createdIncidentId,
        summary: String(createBody.summary),
        status: 'detected',
        next_action: 'triage',
      });
      rows = [created, ...rows];
      await fulfillJson(route, { data: created }, 201);
      return;
    }

    await fulfillJson(route, {
      data: {
        items: rows,
        page_size: 100,
        total: rows.length,
      },
    });
  });

  await page.goto('/admin/incidents');

  await expect(page.getByRole('heading', { name: 'Security incidents' })).toBeVisible();
  await expect(page.getByTestId('admin-nav--admin-incidents')).toBeVisible();
  await expect(page.getByTestId(`admin-incidents-row-${incidentId}`)).toContainText(
    'Admin bulk export anomaly',
  );

  await page.getByTestId('admin-incidents-status-filter').selectOption('triage');
  await expect
    .poll(() =>
      requests.some((url) => url.includes('/admin/incidents') && url.includes('status=triage')),
    )
    .toBe(true);

  await page.getByLabel('Summary').fill('New PIPA incident');
  await page.getByRole('textbox', { name: '사유' }).first().fill('CPO 초기 검토 등록');
  await page.getByTestId('admin-incidents-create').click();

  await expect(page.getByText(`${createdIncidentId} incident를 등록했습니다.`)).toBeVisible();
  expect(createBody).toMatchObject({
    incident_type: 'admin_export_anomaly',
    severity: 'high',
    summary: 'New PIPA incident',
    access_reason: 'CPO 초기 검토 등록',
  });

  await page.getByTestId(`admin-incident-action-triage-${createdIncidentId}`).click();
  await expect(page.getByRole('heading', { name: '상태 조치' })).toBeVisible();
  await page.getByRole('textbox', { name: '사유' }).last().fill('CPO 검토 시작');
  await page.getByTestId('admin-incidents-action-submit').click();

  await expect(
    page.getByText(`${createdIncidentId} incident를 Triage 처리했습니다.`),
  ).toBeVisible();
  expect(triageBody).toMatchObject({ access_reason: 'CPO 검토 시작' });
});
