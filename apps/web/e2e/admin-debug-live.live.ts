import { expect, test, type Page } from '@playwright/test';

const liveEnabled = process.env.PINVI_ADMIN_LIVE_E2E === '1';
const adminEmail = process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword = process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const throttleMs = Number(process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100');
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const rawSecretPatterns = [
  /Authorization\s*[:=]\s*(?:Bearer|Basic)\s+\S+/i,
  /Cookie\s*[:=]\s*\S+/i,
  /Set-Cookie\s*[:=]\s*\S+/i,
  /(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*(?!\[masked\]|%5Bmasked%5D|redacted|<redacted>|\*\*\*)[A-Za-z0-9_./+=-]{8,}/i,
  /AKIA[0-9A-Z]{16}/,
  /BEGIN [A-Z ]*PRIVATE KEY/,
];

let lastActionAt = 0;

async function throttle() {
  if (!Number.isFinite(throttleMs) || throttleMs <= 0) return;
  const elapsed = Date.now() - lastActionAt;
  if (elapsed < throttleMs) {
    await new Promise((resolve) => setTimeout(resolve, throttleMs - elapsed));
  }
  lastActionAt = Date.now();
}

async function loginViaUi(page: Page) {
  if (!adminEmail || !adminPassword) {
    throw new Error('PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD가 필요합니다.');
  }
  await page.goto('/admin/login');
  await page.getByTestId('admin-login-email').fill(adminEmail);
  await page.getByTestId('admin-login-password').fill(adminPassword);
  await throttle();
  await page.getByTestId('admin-login-submit').click();
  await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
  await expect(page.getByTestId('admin-me')).toBeVisible();
}

async function ensureAdminAuth(page: Page) {
  if (!adminStorageState) {
    await loginViaUi(page);
    return;
  }
  await page.goto('/admin');
  await expect(page.getByTestId('admin-me')).toBeVisible();
}

function pathnameOf(value: string) {
  try {
    return new URL(value).pathname;
  } catch {
    return '';
  }
}

function installDebugResponseRecorder(
  page: Page,
  captured: { urls: string[]; requestIds: string[] },
) {
  page.on('response', (response) => {
    const pathname = pathnameOf(response.url());
    if (pathname !== '/admin/debug/logs/system' && pathname !== '/admin/debug/logs/api-calls') {
      return;
    }
    captured.urls.push(response.url());
    const requestId = response.headers()['x-request-id'];
    if (requestId && UUID_RE.test(requestId)) {
      captured.requestIds.push(requestId);
    }
  });
}

async function waitForDebugUrl(
  captured: { urls: string[] },
  predicate: (url: URL) => boolean,
  timeoutMs = 15_000,
) {
  await expect
    .poll(
      () =>
        captured.urls.some((value) => {
          try {
            return predicate(new URL(value));
          } catch {
            return false;
          }
        }),
      { timeout: timeoutMs },
    )
    .toBe(true);
}

async function waitForCapturedRequestId(captured: { requestIds: string[] }, timeoutMs = 15_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const requestId = captured.requestIds.find((value) => UUID_RE.test(value));
    if (requestId) return requestId;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('debug log response에서 X-Request-Id를 찾지 못했습니다.');
}

async function visibleRequestId(page: Page) {
  const bodyText = await page.locator('main').innerText();
  const matches = bodyText.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi);
  return matches?.find((value) => !/^0{8}-0{4}-0{4}-0{4}-0{12}$/i.test(value)) ?? null;
}

async function expectAdminDebugReady(page: Page) {
  await expect(page.getByRole('heading', { name: 'Debug logs' })).toBeVisible();
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('polling');
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('off');
  await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
  await expect(
    page.getByText(/조회 실패|불러오지 못했습니다|Internal Server Error|Forbidden/),
  ).toHaveCount(0);
}

async function expectNoRawSecrets(page: Page) {
  const bodyText = await page.locator('main').innerText();
  for (const pattern of rawSecretPatterns) {
    expect(bodyText).not.toMatch(pattern);
  }
}

test.describe('admin debug live UI e2e', () => {
  test.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  test.skip(
    !adminStorageState && (!adminEmail || !adminPassword),
    'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_STORAGE_STATE가 필요합니다.',
  );
  if (adminStorageState) {
    test.use({ storageState: adminStorageState });
  }
  test.describe.configure({ mode: 'serial' });

  test('debug log polling fallback, filters, timeline search, and masking render on live data', async ({
    page,
  }) => {
    const captured = { urls: [] as string[], requestIds: [] as string[] };
    installDebugResponseRecorder(page, captured);

    await ensureAdminAuth(page);
    await throttle();
    await page.goto('/admin/debug/logs');
    await expectAdminDebugReady(page);
    await expectNoRawSecrets(page);

    await waitForDebugUrl(
      captured,
      (url) =>
        url.pathname === '/admin/debug/logs/system' && url.searchParams.get('page_size') === '50',
    );
    await waitForDebugUrl(
      captured,
      (url) =>
        url.pathname === '/admin/debug/logs/api-calls' &&
        url.searchParams.get('page_size') === '50' &&
        url.searchParams.get('min_status') === '500',
    );

    await page.getByTestId('admin-debug-level').selectOption('all');
    await page.getByTestId('admin-debug-source').fill('api');
    await page.getByTestId('admin-debug-q').fill('request');
    await throttle();
    await page.getByTestId('admin-debug-submit').click();
    await page.getByTestId('admin-debug-method').fill('GET');
    await page.getByTestId('admin-debug-min-status').fill('200');
    await page.getByTestId('admin-debug-path').fill('/v1');
    await throttle();
    await page.getByTestId('admin-debug-refresh').click();
    await expect(page.getByTestId('admin-debug-level')).toHaveValue('all');
    await expect(page.getByTestId('admin-debug-source')).toHaveValue('api');
    await expect(page.getByTestId('admin-debug-q')).toHaveValue('request');
    await expect(page.getByTestId('admin-debug-method')).toHaveValue('GET');
    await expect(page.getByTestId('admin-debug-min-status')).toHaveValue('200');
    await expect(page.getByTestId('admin-debug-path')).toHaveValue('/v1');
    await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });

    await waitForDebugUrl(
      captured,
      (url) =>
        url.pathname === '/admin/debug/logs/system' &&
        url.searchParams.get('source') === 'api' &&
        url.searchParams.get('q') === 'request',
    );
    await waitForDebugUrl(
      captured,
      (url) =>
        url.pathname === '/admin/debug/logs/api-calls' &&
        url.searchParams.get('method') === 'GET' &&
        url.searchParams.get('min_status') === '200' &&
        url.searchParams.get('path') === '/v1',
    );

    const responseCountBeforeLive = captured.urls.length;
    await page.getByTestId('admin-debug-live-toggle').click();
    await expect(page.getByTestId('admin-debug-live-status')).toContainText('live');
    await expect
      .poll(() => captured.urls.length, { timeout: 15_000 })
      .toBeGreaterThan(responseCountBeforeLive);
    await page.getByTestId('admin-debug-live-pause').click();
    await expect(page.getByTestId('admin-debug-live-status')).toContainText('paused');

    const requestId = (await visibleRequestId(page)) ?? (await waitForCapturedRequestId(captured));
    await page.getByTestId('admin-debug-request-id').fill(requestId);
    await throttle();
    await page.getByTestId('admin-debug-request-submit').click();
    await expect(page).toHaveURL(new RegExp(`/admin/debug/request/${requestId}(?:[?#].*)?$`));
    await expect(page.getByRole('heading', { name: 'Request timeline' })).toBeVisible();
    await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
    const summaryVisible = await page
      .getByTestId('admin-request-timeline-summary')
      .isVisible({ timeout: 15_000 })
      .catch(() => false);
    if (summaryVisible) {
      await expect(page.getByTestId('admin-request-source-pinvi_api_call_log')).toBeVisible();
    } else {
      await expect(page.getByText(/source가 없습니다|event가 없습니다/).first()).toBeVisible();
    }
    await expectNoRawSecrets(page);
  });
});
