// ADM-009..014 — users (read-only, fixed accounts never changed), RBAC, audit log, location audit.
// Selectors: admin/users/page.tsx, admin/users/[user_id]/page.tsx, admin/rbac/page.tsx, admin/audit/page.tsx, admin/audit/location/page.tsx
import { expect, test } from '@playwright/test';
import { loginAsAdmin, shot } from '../../helpers/live';
import { isMobileProject, maskedEmail, requireEnv, waitForGet } from '../../helpers/admin';

test.describe('ADM users / audit (read-only)', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(({ isMobile }) => isMobile, 'desktop only');
    await loginAsAdmin(page);
  });

  test('ADM-009 + ADM-010 fixed user is listed masked and its detail page is read-only', async ({ page }) => {
    const email = requireEnv('PINVI_E2E_USER_EMAIL');
    const masked = maskedEmail(email);

    await page.goto('/admin/users');
    await page.getByTestId('admin-users-search').fill(email);
    const listed = waitForGet(page, /\/admin\/users\?.*q=/);
    await page.getByTestId('admin-users-search-submit').click();
    await listed;

    const row = page.locator('[data-testid^="admin-users-row-"]').filter({ hasText: masked }).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText('user');
    // Raw email must never be rendered by the admin list.
    await expect(page.locator('main')).not.toContainText(email);
    const href = await row.getByRole('link', { name: masked }).getAttribute('href');
    expect(href).toMatch(/^\/admin\/users\/[0-9a-f-]{36}$/);
    await shot(page, 'ADM-009', 'list');

    // ADM-010 — detail page, look but do not touch.
    await page.goto(href!);
    await expect(page.getByTestId('admin-user-info')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('admin-user-email')).toContainText(masked);
    await expect(page.getByTestId('admin-user-role-manager')).toBeVisible();
    await expect(page.getByTestId('admin-user-lifecycle-section')).toBeVisible();
    await expect(page.getByTestId('admin-user-sessions')).toBeVisible();
    await expect(page.getByTestId('admin-user-audit-list')).toBeVisible();
    // Guard against accidental mutation: none of these may have been clicked (no confirm dialog open).
    await expect(page.getByTestId('admin-user-destructive-confirm')).toHaveCount(0);
    await expect(page.getByTestId('admin-user-action-reason')).toHaveCount(0);
    await shot(page, 'ADM-010', 'detail');
  });

  test('ADM-011 users status filter is forwarded and rows match', async ({ page }) => {
    await page.goto('/admin/users');
    for (const status of ['disabled', 'active']) {
      const res = waitForGet(page, new RegExp(`/admin/users\\?.*status_filter=${status}`));
      await page.getByTestId('admin-users-status-filter').locator('select').selectOption(status);
      await res;
      const rows = page.locator('[data-testid^="admin-users-row-"]');
      const count = await rows.count();
      for (let i = 0; i < count; i += 1) await expect(rows.nth(i)).toContainText(status);
    }
  });

  test('ADM-012 RBAC page lists the four roles and the permission matrix', async ({ page }) => {
    await page.goto('/admin/rbac');
    await expect(page.getByRole('heading', { name: 'RBAC' })).toBeVisible();
    const roles = page.getByTestId('admin-rbac-roles');
    await expect(roles).toBeVisible({ timeout: 30_000 });
    for (const role of ['admin', 'operator', 'cpo', 'user']) await expect(roles).toContainText(role);
    await expect(page.getByText('권한 매트릭스')).toBeVisible();
  });

  test('ADM-013 audit log lists rows and chain verify responds', async ({ page }) => {
    const list = waitForGet(page, /\/admin\/audit\?limit=100/);
    await page.goto('/admin/audit');
    await list;
    await expect(page.getByRole('heading', { name: '감사 로그' })).toBeVisible();
    const rows = page.locator('[data-testid^="admin-audit-row-"]');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    await expect(rows.first()).toContainText(/\w+\.\w+/); // action like feature_request.reject
    await page.getByTestId('admin-audit-verify').click();
    const result = page.getByTestId('admin-audit-verify-result');
    const error = page.locator('main p.bg-error-bg');
    await expect(result.or(error)).toBeVisible({ timeout: 120_000 });
    if (await result.count()) {
      await expect(result).toContainText(/OK — \d+건 검증 완료|BROKEN — log_id/);
      test.info().annotations.push({ type: 'chain', description: (await result.textContent()) ?? '' });
    } else {
      test.info().annotations.push({ type: 'chain', description: 'verify refused (needs cpo role)' });
    }
    await shot(page, 'ADM-013', 'audit');
  });

  test('ADM-014 location audit filter submits without error', async ({ page }) => {
    await page.goto('/admin/audit/location');
    const today = new Date();
    const yesterday = new Date(today.getTime() - 24 * 3600 * 1000);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    await page.getByTestId('admin-location-from').fill(iso(yesterday));
    await page.getByTestId('admin-location-to').fill(iso(today));
    await page.getByTestId('admin-location-submit').click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('main table, main [role="table"]').first()).toBeVisible({ timeout: 30_000 });
  });
});
