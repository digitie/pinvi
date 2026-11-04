// ADM-001..006 — admin auth: login, role gate (404 not 403 — owner-confirmed, #632 closed), redirects, session refresh.
// Selectors re-verified against origin/main b1cef056:
//   apps/web/app/(admin)/admin/login/page.tsx  -> LoginForm from @kor-travel/ui: data-slot login-username/password/submit/error,
//                                                 wrapper data-testid="admin-login", brand text 'Pinvi Admin'
//   apps/web/app/(admin)/admin/layout.tsx      -> admin-sidebar, admin-me (aria-label '로그인 사용자 <email>'), admin-nav-*
// Contract: apps/api/app/core/rbac.py (non-admin => 404 RESOURCE_NOT_FOUND), apps/api/app/api/v1/auth.py (/auth/refresh)
// Ordinary-user identity: PINVI_E2E_USER2_* (test2@test.com) when provisioned, else PINVI_E2E_USER_*.
import { expect, test } from '@playwright/test';
import { shot, isMobileProject } from '../../helpers/live';
import { ADMIN_LOGIN, captureApiOrigin, loginAsOrdinaryUser, newAdminActor, ordinaryUserCreds, requireEnv } from '../../helpers/admin';

test.describe('ADM auth', () => {
  test('ADM-001 admin login lands on /admin with sidebar identity', async ({ page }) => {
    test.skip(isMobileProject(), 'desktop only');
    const email = requireEnv('PINVI_E2E_ADMIN_EMAIL');
    const password = requireEnv('PINVI_E2E_ADMIN_PASSWORD');

    await page.goto('/admin/login');
    await expect(page.locator(ADMIN_LOGIN.root)).toBeVisible();
    await expect(page.getByText('Pinvi Admin', { exact: true })).toBeVisible();
    await page.locator(ADMIN_LOGIN.username).fill(email);
    await page.locator(ADMIN_LOGIN.password).fill(password);
    await page.locator(ADMIN_LOGIN.submit).click();

    await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/, { timeout: 30_000 });
    await expect(page.getByTestId('admin-sidebar')).toBeVisible();
    // Value compared only; never logged.
    await expect(page.getByTestId('admin-me')).toHaveAttribute('aria-label', `로그인 사용자 ${email}`);
    for (const href of ['/admin/feature-requests', '/admin/features', '/admin/dedup-review', '/admin/integrity', '/admin/audit']) {
      await expect(page.getByTestId(`admin-nav-${href.replace(/[^a-z0-9]+/gi, '-')}`)).toBeVisible();
    }
    await shot(page, 'ADM-001', 'dashboard');
  });

  test('ADM-002 ordinary-user credentials on /admin/login are refused and the session is dropped', async ({ page }) => {
    test.skip(isMobileProject(), 'desktop only');
    const creds = ordinaryUserCreds();
    test.info().annotations.push({ type: 'identity', description: creds.label });
    // The login page never calls /auth/me, so capture the API origin from the login/logout calls themselves.
    let origin: string | null = process.env.PINVI_E2E_API_URL ?? null;
    page.on('request', (req) => {
      if (!origin && /\/auth\/(login|logout)$/.test(req.url())) origin = new URL(req.url()).origin;
    });

    const logoutSeen = page.waitForRequest((req) => req.method() === 'POST' && /\/auth\/logout$/.test(req.url()), { timeout: 30_000 });
    await page.goto('/admin/login');
    await page.locator(ADMIN_LOGIN.username).fill(creds.email);
    await page.locator(ADMIN_LOGIN.password).fill(creds.password);
    await page.locator(ADMIN_LOGIN.submit).click();

    const err = page.locator(ADMIN_LOGIN.error);
    await expect(err).toHaveText('관리자 권한이 없는 계정입니다.');
    await expect(err).toHaveAttribute('role', 'alert');
    await expect(page).toHaveURL(/\/admin\/login(?:[?#].*)?$/);
    await logoutSeen;
    expect(origin, 'API origin should have been observed from /auth/login').not.toBeNull();
    const me = await page.request.get(`${origin}/auth/me`);
    expect(me.status(), 'session must be gone after refused admin login').toBe(401);
    await shot(page, 'ADM-002', 'refused');
  });

  test('ADM-003 ordinary-user session is redirected away from /admin with reason=forbidden', async ({ page }) => {
    await loginAsOrdinaryUser(page);
    for (const route of ['/admin', '/admin/users', '/admin/feature-requests']) {
      await page.goto(route);
      await expect(page).toHaveURL(/\/admin\/login\?reason=forbidden$/, { timeout: 30_000 });
      const err = page.locator(ADMIN_LOGIN.error);
      await expect(err).toHaveText('관리자 권한이 필요합니다.');
      await expect(err).toHaveAttribute('role', 'alert');
      await expect(page.locator('[data-testid^="admin-users-row-"], [data-testid^="admin-fr-row-"]')).toHaveCount(0);
    }
    await shot(page, 'ADM-003', 'forbidden');
  });

  test('ADM-004 ordinary-user session calling admin API gets 404 RESOURCE_NOT_FOUND (not 403)', async ({ page }) => {
    test.skip(isMobileProject(), 'desktop only');
    // Owner decision 2026-11-03 (#632 closed, no change): admin routes hide their existence from
    // non-admin sessions — 404 RESOURCE_NOT_FOUND is the contract (rbac.py SPEC V8 M-4).
    const apiOrigin = captureApiOrigin(page);
    await loginAsOrdinaryUser(page);
    // Any app page triggers /auth/me, which reveals the API origin.
    await page.goto('/trips');
    const origin = await apiOrigin();
    for (const path of ['/admin/users?page=1&limit=1', '/admin/feature-requests?status=pending&page=1&limit=1', '/admin/audit?limit=1']) {
      const res = await page.request.get(`${origin}${path}`);
      expect(res.status(), `${path} must hide existence`).toBe(404);
      const body = (await res.json()) as { error?: { code?: string } };
      expect(body.error?.code).toBe('RESOURCE_NOT_FOUND');
    }
  });

  test('ADM-005 anonymous /admin goes to /admin/login', async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await page.goto('/admin');
      await expect(page).toHaveURL(/\/admin\/login$/, { timeout: 30_000 });
      await expect(page.locator(ADMIN_LOGIN.root)).toBeVisible();
      // LoginForm always renders the error slot as an empty role=alert live region.
      await expect(page.locator(ADMIN_LOGIN.error)).toHaveText('');
    } finally {
      await context.close();
    }
  });

  test('ADM-006 admin session refresh keeps admin pages working', async ({ browser }) => {
    test.skip(isMobileProject(), 'desktop only');
    const admin = await newAdminActor(browser);
    try {
      const origin = await admin.apiOrigin();
      const res = await admin.page.request.post(`${origin}/auth/refresh`);
      expect(res.status()).toBe(200);
      const body = (await res.json()) as { data: { roles: string[] } };
      expect(body.data.roles.some((r) => ['admin', 'operator', 'cpo'].includes(r))).toBe(true);

      await admin.page.goto('/admin/users');
      await expect(admin.page).toHaveURL(/\/admin\/users$/);
      await expect(admin.page.locator('[data-testid^="admin-users-row-"]').first()).toBeVisible({ timeout: 30_000 });
      await shot(admin.page, 'ADM-006', 'after-refresh');
    } finally {
      await admin.context.close();
    }
  });
});
