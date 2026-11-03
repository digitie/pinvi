// ADM-022..027 — dedup review, integrity, debug logs, API call logs: READ-ONLY on prod.
// Verdict / issue-action submits are never clicked (Map merge and issue resolve are not reversible).
// Selectors: admin/dedup-review/page.tsx, admin/integrity/page.tsx, admin/debug/logs/page.tsx, admin/api-calls/page.tsx
import { expect, test } from '@playwright/test';
import { appAlerts, loginAsAdmin, shot, isMobileProject } from '../../helpers/live';
import { adminSelect, waitForGet } from '../../helpers/admin';

test.describe('ADM dedup / integrity / debug (read-only)', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(isMobileProject(), 'desktop only');
    await loginAsAdmin(page);
  });

  test('ADM-022 + ADM-023 dedup review list, detail panel, filter forwarding', async ({ page }) => {
    test.fail(true, '#651: GET /admin/dedup-review → 422 FORBIDDEN (Map rejects PinVi), page looks like an empty queue');
    const list = waitForGet(page, /\/admin\/dedup-review/);
    await page.goto('/admin/dedup-review');
    // soft: keep checking filter forwarding (ADM-023) even while the list itself fails (#651)
    expect.soft((await list).status(), 'GET /admin/dedup-review').toBe(200);
    await expect(page.getByRole('heading', { name: 'Dedup review' })).toBeVisible();
    const rows = page.locator('[data-testid^="admin-dedup-row-"]');
    if (await rows.count()) {
      await rows.first().click();
      const detail = page.getByTestId('admin-dedup-detail');
      await expect(detail).toBeVisible();
      await expect(detail.locator('[data-testid^="admin-dedup-master-"]')).toHaveCount(2);
      await expect(detail).toContainText(/\d+(\.\d+)?/);
      // Verdict is never submitted on prod.
      await expect(page.getByTestId('admin-dedup-mutation-notice')).toHaveCount(0);
    } else {
      test.info().annotations.push({ type: 'data', description: 'dedup queue empty on prod' });
    }
    await shot(page, 'ADM-022', 'dedup');

    // ADM-023
    await page.getByTestId('admin-dedup-search').fill('seoul');
    await page.getByTestId('admin-dedup-min-score').fill('85');
    // Forwarding is a request-side contract (typing min_score already refetches without q, and the list
    // may answer 4xx — see catalog notes): wait for the submitted request that carries both params.
    const isDedupGet = (r: { method(): string; url(): string }, re: RegExp) => r.method() === 'GET' && re.test(r.url());
    const filtered = page.waitForRequest((r) => isDedupGet(r, /\/admin\/dedup-review\?(?=.*q=seoul)(?=.*min_score=85)/), { timeout: 30_000 });
    await page.getByTestId('admin-dedup-submit').click();
    const url = new URL((await filtered).url());
    expect(url.searchParams.get('q')).toBe('seoul');
    expect(url.searchParams.get('min_score')).toBe('85');
    const statusReq = page.waitForRequest((r) => isDedupGet(r, /\/admin\/dedup-review\?.*status=accepted/), { timeout: 30_000 });
    await adminSelect(page, 'admin-dedup-status').selectOption('accepted');
    expect(new URL((await statusReq).url()).searchParams.getAll('status')).toContain('accepted');
    await expect(page.getByTestId('admin-dedup-mutation-notice')).toHaveCount(0);
  });

  test('ADM-024 + ADM-025 integrity issues/reports, pinvi_app read-only rows, filter forwarding', async ({ page }) => {
    const issues = waitForGet(page, /\/admin\/integrity\/issues/);
    const reports = waitForGet(page, /\/admin\/integrity\/reports/);
    await page.goto('/admin/integrity');
    await issues;
    await reports;
    await expect(page.getByRole('heading', { name: '정합성' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Issues', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Reports', exact: true })).toBeVisible();

    const appIssues = waitForGet(page, /\/admin\/integrity\/issues\?.*source=pinvi_app/);
    await adminSelect(page, 'admin-integrity-source').selectOption('pinvi_app');
    await appIssues;
    const appRows = page.locator('[data-testid^="admin-integrity-issue-row-"]');
    const n = await appRows.count();
    for (let i = 0; i < Math.min(n, 10); i += 1) {
      await expect(appRows.nth(i)).toContainText('read-only');
      await expect(appRows.nth(i).locator('[data-testid^="admin-integrity-action-"]')).toHaveCount(0);
    }
    test.info().annotations.push({ type: 'data', description: `pinvi_app issues: ${n}` });
    await shot(page, 'ADM-024', 'integrity');

    // ADM-025
    await adminSelect(page, 'admin-integrity-source').selectOption('all');
    const statusRes = waitForGet(page, /\/admin\/integrity\/issues\?.*status=acknowledged/);
    await adminSelect(page, 'admin-integrity-status').selectOption('acknowledged');
    await statusRes;
    const sevRes = waitForGet(page, /\/admin\/integrity\/issues\?.*severity=critical/);
    await adminSelect(page, 'admin-integrity-severity').selectOption('critical');
    const sev = new URL((await sevRes).url());
    expect(sev.searchParams.get('status')).toBe('acknowledged');
    expect(sev.searchParams.get('severity')).toBe('critical');
    const provRes = waitForGet(page, /\/admin\/integrity\/issues\?.*provider=visitkorea/);
    await page.getByTestId('admin-integrity-provider').fill('visitkorea');
    await provRes;
    const repRes = waitForGet(page, /\/admin\/integrity\/reports\?.*severity_max=ERROR/);
    await adminSelect(page, 'admin-integrity-report-severity').selectOption('ERROR');
    await repRes;
    await expect(page.getByTestId('admin-integrity-action-dialog')).toHaveCount(0);
  });

  test('ADM-026 debug logs: polling status, filters, request timeline, no raw secrets', async ({ page }) => {
    let requestId: string | null = null;
    page.on('response', (res) => {
      if (!requestId && /\/admin\//.test(res.url())) requestId = res.headers()['x-request-id'] ?? null;
    });
    const status = waitForGet(page, /\/admin\/debug\/logs\/stream\/status/);
    await page.goto('/admin/debug/logs');
    await status;
    await expect(page.getByRole('heading', { name: 'Debug logs' })).toBeVisible();
    await expect(page.getByTestId('admin-debug-live-status')).toContainText(/polling|sse/);
    await expect(page.getByText('System logs')).toBeVisible();
    await expect(page.getByText('API call logs')).toBeVisible();

    // Filters refetch as you type — register the waits first and match the final query shape.
    const sys = waitForGet(page, /\/admin\/debug\/logs\/system\?(?=.*level=error)(?=.*q=timeout)/);
    const api = waitForGet(page, /\/admin\/debug\/logs\/api-calls\?(?=.*method=GET)(?=.*min_status=500)/);
    await adminSelect(page, 'admin-debug-level').selectOption('error');
    await page.getByTestId('admin-debug-q').fill('timeout');
    await page.getByTestId('admin-debug-method').fill('GET');
    await page.getByTestId('admin-debug-min-status').fill('500');
    await page.getByTestId('admin-debug-submit').click();
    expect(new URL((await sys).url()).searchParams.get('level')).toBe('error');
    expect(new URL((await api).url()).searchParams.get('method')).toBe('GET');

    if (requestId && /^[0-9a-f-]{36}$/.test(requestId)) {
      await page.getByTestId('admin-debug-request-id').fill(requestId);
      await page.getByTestId('admin-debug-request-submit').click();
      await expect(page.getByRole('heading', { name: 'Request timeline' })).toBeVisible({ timeout: 30_000 });
      // A timeline exists only for requests the log pipeline captured; an arbitrary admin request id may
      // have none — then the page must show an error box, never a crash.
      const summary = page.getByTestId('admin-request-timeline-summary');
      await expect(summary.or(appAlerts(page).first())).toBeVisible({ timeout: 15_000 });
      test.info().annotations.push({ type: 'data', description: `request timeline: ${(await summary.count()) ? 'summary' : 'not captured (error box)'}` });
    } else {
      test.info().annotations.push({ type: 'data', description: 'no X-Request-Id header captured; timeline step skipped' });
    }
    const text = (await page.locator('main').textContent()) ?? '';
    expect(text).not.toMatch(/service_key=|token=[A-Za-z0-9]{8,}|password/i);
    await shot(page, 'ADM-026', 'debug-logs');
  });

  test('ADM-027 API call log page filters by provider', async ({ page }) => {
    await page.goto('/admin/api-calls');
    await expect(page.getByRole('heading', { name: 'API 호출 로그' })).toBeVisible();
    await page.getByTestId('admin-api-calls-provider').fill('kor_travel_map');
    const res = waitForGet(page, /\/admin\/api-calls/);
    await page.getByTestId('admin-api-calls-submit').click();
    await res;
    // `admin-api-calls-error` is the "Error" filter input, not an error panel.
    await expect(appAlerts(page)).toHaveCount(0);
  });
});
