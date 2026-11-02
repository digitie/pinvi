// Shared, area-local helpers for the ADM specs. Everything that other areas may
// also want is listed in README "helpers needed" so the integrator can lift it
// into ../helpers/live.
import { expect, type Browser, type BrowserContext, type Page, type Response } from '@playwright/test';
import { apiBaseURL, isMobileProject, loginAs, loginAsAdmin, loginAsUser, requireEnv, waitForGet } from './live';

export { isMobileProject, requireEnv, waitForGet };

export const E2E = '[e2e]';

/**
 * The "ordinary user" identity for the role-gate cases (ADM-002/003/004).
 * Prefers the second test account (PINVI_E2E_USER2_*) when provisioned so the primary
 * test@test.com session used by trip/POI writers is never bounced; falls back to PINVI_E2E_USER_*.
 */
export function ordinaryUserCreds(): { email: string; password: string; label: 'user2' | 'user' } {
  const email2 = process.env.PINVI_E2E_USER2_EMAIL;
  const password2 = process.env.PINVI_E2E_USER2_PASSWORD;
  if (email2 && password2) return { email: email2, password: password2, label: 'user2' };
  return { email: requireEnv('PINVI_E2E_USER_EMAIL'), password: requireEnv('PINVI_E2E_USER_PASSWORD'), label: 'user' };
}

/**
 * Logs in as the ordinary user through the public /login form
 * (apps/web/app/(auth)/login/page.tsx on origin/main: login-email / login-password / login-submit).
 * Uses loginAsUser() from the shared helpers when no second account is configured.
 */
export async function loginAsOrdinaryUser(page: Page): Promise<void> {
  const creds = ordinaryUserCreds();
  if (creds.label === 'user') {
    await loginAsUser(page);
    return;
  }
  await loginAs(page, creds.email, creds.password);
}

/**
 * Admin login form selectors on origin/main (b1cef056): the page renders `LoginForm` from `@kor-travel/ui`
 * (vendored tgz), which exposes `data-slot` attributes instead of per-field test ids —
 * see apps/web/e2e/admin-login.e2e.ts on origin/main.
 */
export const ADMIN_LOGIN = {
  root: '[data-testid="admin-login"]',
  username: '[data-slot="login-username"]',
  password: '[data-slot="login-password"]',
  submit: '[data-slot="login-submit"]',
  error: '[data-slot="login-error"]',
} as const;

/** Short unique tag so parallel/repeated runs never collide on titles. */
export function runTag(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/** mask_email() from apps/api/app/services/admin_users.py — local[0] + '***@' + domain. */
export function maskedEmail(email: string): string {
  const [local, domain] = email.split('@');
  if (!domain) return email;
  return local.length <= 1 ? `${local}***@${domain}` : `${local[0]}***@${domain}`;
}

/**
 * API base (origin + path prefix) baked into the web build — delegates to the shared
 * `apiBaseURL`, which learns it from the page's own traffic (or `PINVI_E2E_API_URL`).
 */
export function captureApiOrigin(page: Page): () => Promise<string> {
  return () => apiBaseURL(page);
}

export interface Actor {
  context: BrowserContext;
  page: Page;
  apiOrigin: () => Promise<string>;
}

export async function newAdminActor(browser: Browser, viewport?: { width: number; height: number }): Promise<Actor> {
  const context = await browser.newContext(viewport ? { viewport } : {});
  const page = await context.newPage();
  const apiOrigin = captureApiOrigin(page);
  await loginAsAdmin(page);
  return { context, page, apiOrigin };
}

export async function newUserActor(browser: Browser, viewport?: { width: number; height: number }): Promise<Actor> {
  const context = await browser.newContext(viewport ? { viewport } : {});
  const page = await context.newPage();
  const apiOrigin = captureApiOrigin(page);
  await loginAsUser(page);
  return { context, page, apiOrigin };
}

/** Asserts that the Next.js runtime error overlay / error page is not shown. */
export async function expectNoRuntimeError(page: Page): Promise<void> {
  await expect(page.getByText(/Application error|Unhandled Runtime Error|Internal Server Error/)).toHaveCount(0);
}

/** No horizontal page scroll at phone width (same gate PinVi mocked e2e uses). */
export async function expectNoRootHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

/**
 * Creates a `[e2e]`-prefixed new_place feature suggestion as the USER via the map deep link
 * (/map?suggest=lon,lat → FeatureRequestDialog). Returns the suggestion request_id.
 * NOTE: there is no delete endpoint for suggestions; callers must reject it as admin (see README).
 */
export async function createE2eSuggestion(
  user: Actor,
  opts: { lon: number; lat: number; title: string; categories?: string; note?: string },
): Promise<string> {
  if (!opts.title.startsWith(E2E)) throw new Error('suggestion title must start with [e2e]');
  const { page } = user;
  const responsePromise = page.waitForResponse(
    (res) => res.request().method() === 'POST' && /\/features\/requests$/.test(new URL(res.url()).pathname),
    { timeout: 60_000 },
  );
  await page.goto(`/map?suggest=${opts.lon},${opts.lat}`);
  const dialog = page.getByTestId('feature-request-dialog');
  await expect(dialog).toBeVisible({ timeout: 30_000 });
  await dialog.getByLabel('이름').fill(opts.title);
  if (opts.categories) await dialog.getByLabel('카테고리(쉼표 구분, 선택)').fill(opts.categories);
  if (opts.note) await dialog.getByLabel('메모(선택)').fill(opts.note);
  await page.getByTestId('feature-request-submit').click();
  const res = await responsePromise;
  expect(res.status(), 'POST /features/requests should be 201 (or 200 on per-user dedup)').toBeLessThan(300);
  const body = (await res.json()) as { data: { request_id: string; status: string } };
  await expect(dialog).toContainText('제안이 접수됐습니다');
  return body.data.request_id;
}

/** Opens the admin review dialog for a suggestion from the Feature 제안 queue (desktop table row). */
export async function openReviewDialog(admin: Page, requestId: string, statusFilter = 'pending'): Promise<void> {
  await admin.goto('/admin/feature-requests');
  await expect(admin.getByRole('heading', { name: 'Feature 제안 검토' })).toBeVisible();
  if (statusFilter !== 'pending') {
    await admin.getByTestId('admin-fr-status-filter').locator('select').selectOption(statusFilter);
  }
  await waitForGet(admin, /\/admin\/feature-requests/);
  await expect(admin.getByTestId(`admin-fr-row-${requestId}`)).toBeVisible({ timeout: 30_000 });
  await admin.getByTestId(`admin-fr-review-${requestId}`).click();
  await expect(admin.getByTestId('admin-fr-review-dialog')).toBeVisible();
}

/** Admin-side cleanup for a pending [e2e] suggestion: reject with an [e2e] reason. Terminal, no Map call. */
export async function rejectSuggestionAsAdmin(admin: Page, requestId: string, reason: string): Promise<void> {
  if (!reason.startsWith(E2E)) throw new Error('reject reason must start with [e2e]');
  await openReviewDialog(admin, requestId, 'pending');
  await admin.getByTestId('admin-fr-reason').fill(reason);
  await admin.getByTestId('admin-fr-reject').click();
  await expect(admin.getByTestId('admin-fr-reject-confirm')).toBeVisible();
  await expect(admin.getByTestId('admin-fr-reject-reason-preview')).toHaveText(reason);
  const responsePromise = admin.waitForResponse(
    (res) => res.request().method() === 'POST' && new URL(res.url()).pathname.endsWith(`/admin/feature-requests/${requestId}/reject`),
  );
  await admin.getByTestId('admin-fr-reject-confirm-confirm').click();
  const res = await responsePromise;
  expect(res.status()).toBe(200);
  await expect(admin.getByTestId('admin-fr-notice')).toHaveText('제안을 거절했습니다.');
}
