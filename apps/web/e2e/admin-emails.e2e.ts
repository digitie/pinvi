import { expect, test, type Page, type Route } from '@playwright/test';

const operatorUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'operator@example.com',
  nickname: 'Operator',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'operator'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

async function mockOperatorAuth(page: Page) {
  await page.route(/.*\/auth\/me$/, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: operatorUser }),
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

test('Admin emails page가 deliverability와 suppression 상태를 렌더링한다', async ({ page }) => {
  await mockOperatorAuth(page);

  await page.route(/.*\/admin\/emails\/deliverability$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    await fulfillJson(route, {
      data: {
        generated_at: '2026-06-28T10:00:00+09:00',
        status: 'degraded',
        resend_api_configured: false,
        console_mode: true,
        domain: {
          from_email: 'Pinvi <noreply@send.pinvi.test>',
          from_domain: 'send.pinvi.test',
          domain_status: null,
          sending_capability: null,
          domain_matched: null,
          domains_checked: 0,
          error_class: null,
        },
        webhook: {
          signature_configured: false,
          unsigned_allowed: false,
          latest_processed_at: '2026-06-28T09:55:00+09:00',
          recent_events: { 'email.bounced': 2, 'email.complained': 1 },
        },
        suppression: {
          active_suppressions: 3,
          released_suppressions: 1,
          users_by_email_status: { active: 10, bounced: 1, complained: 1, suppressed: 1 },
        },
        queue: {
          pending: 1,
          sent: 2,
          delivered: 3,
          delivery_delayed: 1,
          bounced: 2,
          complained: 1,
          suppressed: 3,
          failed: 1,
        },
        checks: [
          { key: 'resend_api', label: 'Resend API', status: 'error', message: 'console mode' },
          { key: 'dns_records', label: 'SPF/DKIM/DMARC', status: 'warn', message: null },
          { key: 'webhook_signature', label: 'Webhook signature', status: 'error', message: null },
        ],
      },
    });
  });

  await page.route(/.*\/admin\/emails(\?.*)?$/, async (route) => {
    if (await continueIfWebRequest(route)) return;
    await fulfillJson(route, {
      data: [
        {
          email_id: '11111111-1111-4111-8111-111111111111',
          to_email: 'suppressed@pinvi.test',
          template: 'trip_invite',
          status: 'suppressed',
          attempts: 1,
          last_error: 'suppressed:suppression:complaint',
          resend_id: null,
          bounce_type: null,
          scheduled_at: '2026-06-28T09:50:00+09:00',
          sent_at: null,
        },
      ],
    });
  });

  await page.goto('/admin/emails');

  await expect(page.getByRole('heading', { name: '이메일 큐' })).toBeVisible();
  await expect(page.getByTestId('admin-email-deliverability-status')).toContainText('degraded');
  await expect(page.getByTestId('admin-email-domain-status')).toContainText('-');
  await expect(page.getByTestId('admin-email-suppression-count')).toContainText('3');
  await expect(page.getByTestId('admin-email-checks')).toContainText('Resend API');
  await expect(
    page.getByTestId('admin-emails-row-11111111-1111-4111-8111-111111111111'),
  ).toContainText('suppressed');

  await page.getByTestId('admin-emails-status-filter').selectOption('suppressed');
  await expect(page.getByTestId('admin-emails-status-filter')).toHaveValue('suppressed');
});
