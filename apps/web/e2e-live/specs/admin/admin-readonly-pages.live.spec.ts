// ADM-007 dashboard, ADM-008 route sweep (desktop + mobile), ADM-040 sidebar a11y, ADM-045 mobile drawer + top bar title.
// Selectors re-verified on origin/main b1cef056: apps/web/app/(admin)/admin/page.tsx (admin-stat-*, admin-system-*),
// admin/layout.tsx (NAV_GROUPS hrefs unchanged, admin-me, admin-nav-* via CommonDocumentLink). The shell is the common
// @kor-travel/ui 0.2.3 AdminShell: rail [data-slot=admin-shell-rail] (lg+), left drawer via [data-slot=admin-shell-menu-button]
// (< lg), one-line top bar h1 [data-slot=admin-shell-title] = "영역 - 페이지" outside <main>.
import { expect, test } from '@playwright/test';
import { appAlerts, loginAsAdmin, shot } from '../../helpers/live';
import {
  ADMIN_SHELL,
  adminNavLink,
  closeAdminDrawer,
  expectNoRootHorizontalScroll,
  expectNoRuntimeError,
  isMobileProject,
  waitForGet,
} from '../../helpers/admin';

// NAV_GROUPS hrefs minus dev-only (seed/reset) and the iframe/backup pages PinVi already covers in its own live suite.
const ROUTES = [
  '/admin',
  '/admin/users',
  '/admin/rbac',
  '/admin/trips',
  '/admin/pois',
  '/admin/notice-plans',
  '/admin/files',
  '/admin/feature-requests',
  '/admin/feature-reference-reconciliations',
  '/admin/audit',
  '/admin/incidents',
  '/admin/abuse',
  '/admin/dsr',
  '/admin/moderation',
  '/admin/features',
  '/admin/dedup-review',
  '/admin/provider-sync',
  '/admin/integrity',
  '/admin/category-mapping',
] as const;

test.describe('ADM read-only pages', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('ADM-041 attachment retention status and confirmation remain read only', async ({ page }) => {
    const status = waitForGet(page, /\/admin\/storage-retention(?:\?|$)/);
    await page.goto('/admin/retention');
    await status;
    const panel = page.getByTestId('storage-retention');
    await expect(panel).toContainText('30일');
    await expect(panel).toContainText('기한 지난 여행');
    const run = panel.getByRole('button', { name: '기한 지난 여행·파일 정리' });
    if (await run.count()) {
      await expect(run).toBeDisabled();
      await panel.getByLabel('첨부 정리 사유').fill('카탈로그 확인창만 검증');
      await panel.getByLabel(/확인 문구:/).fill('DELETE EXPIRED FILES');
      await run.click();
      const confirm = page.getByRole('alertdialog');
      await expect(confirm).toBeVisible();
      await expect(confirm).toContainText('복원할 수 없습니다');
      await confirm.getByRole('button', { name: '취소', exact: true }).click();
      await expect(page.getByRole('alertdialog')).toHaveCount(0);
    }
    await expectNoRuntimeError(page);
    if (isMobileProject()) await expectNoRootHorizontalScroll(page);
    await shot(page, 'ADM-041', 'attachment-retention');
  });

  test('ADM-007 dashboard stat strip and system board', async ({ page }) => {
    const stats = waitForGet(page, /\/admin\/stats/);
    await page.goto('/admin');
    await stats;
    await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
    const cards = page.locator('[data-testid^="admin-stat-"]');
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThanOrEqual(9);
    const users = page.getByTestId('admin-stat-사용자 총 수');
    await expect(users).toBeVisible();
    await expect(users).not.toContainText('—', { timeout: 30_000 });
    await expect(users).toContainText(/\d/);
    await expect(page.locator('[data-testid^="admin-system-"]').first()).toBeVisible({ timeout: 30_000 });
    await expect(appAlerts(page)).toHaveCount(0);
    await shot(page, 'ADM-007', 'dashboard');
  });

  test('ADM-008 every admin nav route renders without a runtime error', async ({ page }) => {
    test.setTimeout(170_000);
    for (const route of ROUTES) {
      await page.goto(route);
      await expect(page).toHaveURL(new RegExp(`${route.replace(/\//g, '\\/')}(\\?.*)?$`), { timeout: 30_000 });
      // The page title lives in the shell's one-line top bar (outside <main>) as "영역 - 페이지".
      const title = page.locator(ADMIN_SHELL.title);
      await expect(title).toBeVisible({ timeout: 30_000 });
      await expect(title).toHaveText(/\S - \S/);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expectNoRuntimeError(page);
      // The menu link for this route exists (rail on desktop, left drawer on mobile — both render @kor-travel/ui
      // AppMenu with CommonDocumentLink -> data-testid="admin-nav-<href>"). aria-current is owned by the vendored
      // menu component, so it is recorded as an annotation rather than asserted.
      const link = await adminNavLink(page, route);
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute('href', route);
      const current = await link
        .evaluate((el) => el.closest('nav')?.querySelector('[aria-current="page"]')?.getAttribute('href') ?? null)
        .catch(() => null);
      if (current !== route) test.info().annotations.push({ type: 'nav-active', description: `${route}: aria-current on ${current ?? 'none'}` });
      await closeAdminDrawer(page);
      if (isMobileProject()) await expectNoRootHorizontalScroll(page);
      // Shared 60/min authenticated rate limit: each admin page fires /auth/me + its own queries.
      await page.waitForTimeout(1_500);
    }
    await shot(page, 'ADM-008', 'last-route');
  });

  test('ADM-040 sidebar collapse persists and skip link is first in tab order', async ({ page }) => {
    test.skip(isMobileProject(), 'toggle is lg-only');
    await page.goto('/admin/users');
    const rail = page.locator(ADMIN_SHELL.rail);
    const toggle = page.locator(ADMIN_SHELL.collapse);
    await expect(rail).toBeVisible();
    await expect(rail).not.toHaveAttribute('data-collapsed', 'true');
    try {
      await toggle.click();
      await expect(rail).toHaveAttribute('data-collapsed', 'true');
      await expect(toggle).toHaveAttribute('aria-expanded', 'false');
      await page.reload();
      await expect(page.locator(ADMIN_SHELL.rail)).toHaveAttribute('data-collapsed', 'true');
      await page.keyboard.press('Tab');
      const focusedHref = await page.evaluate(() => (document.activeElement as HTMLAnchorElement | null)?.getAttribute('href') ?? '');
      // The shell skip link targets #<ADMIN_MAIN_CONTENT_ID> (admin-main-content).
      expect(focusedHref.startsWith('#'), 'first Tab should land on the skip link').toBe(true);
    } finally {
      await page.evaluate(() => window.localStorage.setItem('pinvi.admin.sidebar.collapsed', '0'));
      await page.reload();
      await expect(page.locator(ADMIN_SHELL.rail)).not.toHaveAttribute('data-collapsed', 'true');
    }
  });

  test('ADM-045 mobile menu folds into a left drawer and the top bar holds only "영역 - 페이지"', async ({ page }) => {
    test.skip(!isMobileProject(), 'drawer is below lg only');
    await page.goto('/admin/users');
    await expect(page.locator(ADMIN_SHELL.rail)).toBeHidden();
    await expect(page.locator(ADMIN_SHELL.title)).toHaveText('Pinvi 운영 - 사용자');
    expect((await page.locator(ADMIN_SHELL.header).boundingBox())?.height ?? 0).toBeLessThanOrEqual(56);
    await page.locator(ADMIN_SHELL.menuButton).click();
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();
    await expect.poll(async () => (await drawer.boundingBox())?.x ?? -1).toBe(0);
    expect((await drawer.boundingBox())?.width ?? 0).toBeLessThanOrEqual(280);
    await expect(drawer.getByTestId('admin-nav--admin-users')).toHaveAttribute('aria-current', 'page');
    await shot(page, 'ADM-045', 'drawer-open');
    await page.keyboard.press('Escape');
    await expect(drawer).toHaveCount(0);
    await expect(page.locator(ADMIN_SHELL.menuButton)).toBeFocused();
    await expectNoRootHorizontalScroll(page);
  });
});
