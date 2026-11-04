// ADM-032..036 — the REVERSIBLE part of "POI 승격": user files an [e2e] 장소 제안, admin reviews it.
// Approve is exercised only in the two paths that make NO Map call and do NOT change status:
//   (1) empty reason  -> client-side validation, no request          (ADM-032)
//   (2) lat > 39.5    -> PinVi validate_submission 422 before Map     (ADM-033)
// Every suggestion created here ends as terminal `rejected` (ADM-034 / cleanup). There is no delete endpoint
// for suggestions (apps/api/app/api/v1/features.py has only GET/POST), so a rejected [e2e] row remains in
// app.feature_suggestions. The whole file is therefore gated by PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS=1.
// Full approve (ADM-031) is BLOCKED — see catalog.yaml / README.
// Selectors: admin/feature-requests/page.tsx, components/map/FeatureRequestDialog.tsx
import { expect, test } from '@playwright/test';
import { appAlerts, shot, isMobileProject } from '../../helpers/live';
import {
  E2E,
  createE2eSuggestion,
  maskedEmail,
  newAdminActor,
  newUserActor,
  openReviewDialog,
  rejectSuggestionAsAdmin,
  requireEnv,
  runTag,
  waitForGet,
  type Actor,
  adminSelect,
} from '../../helpers/admin';

const HAHOE = { lon: 128.5188, lat: 36.5392 }; // 안동하회마을 (heritage) — inside Map range
const OUT_OF_MAP_RANGE = { lon: 128.0, lat: 41.0 }; // PinVi Coord allows lat<=43, Map queue requires lat<=39.5

const gated = () => process.env.PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS !== '1';

test.describe.serial('ADM promotion review (desktop)', () => {
  let user: Actor;
  let admin: Actor;
  let tag = '';
  let pendingId = ''; // ADM-032 → rejected in ADM-034
  let outOfRangeId = ''; // ADM-033 → rejected in ADM-033 cleanup

  test.beforeAll(async ({ browser }) => {
    test.skip(isMobileProject(), 'desktop only');
    test.skip(gated(), 'set PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS=1 to accept residual rejected [e2e] suggestion rows');
    user = await newUserActor(browser);
    admin = await newAdminActor(browser);
    tag = runTag();
  });

  test.afterAll(async () => {
    // Belt and braces: anything still pending gets rejected so no [e2e] row sits in the admin queue.
    try {
      for (const id of [pendingId, outOfRangeId]) {
        if (!id) continue;
        await rejectSuggestionAsAdmin(admin.page, id, `${E2E} cleanup ${tag}`).catch(() => undefined);
      }
    } finally {
      await user?.context.close();
      await admin?.context.close();
    }
  });

  test('ADM-032 review dialog shows the [e2e] suggestion; empty-reason approve is blocked client-side', async () => {
    const masked = maskedEmail(requireEnv('PINVI_E2E_USER_EMAIL'));
    const title = `${E2E} ADM-032 ${tag}`;
    pendingId = await createE2eSuggestion(user, { ...HAHOE, title, categories: '카페', note: `${E2E} promotion review` });

    const page = admin.page;
    await openReviewDialog(page, pendingId, 'pending');
    const dialog = page.getByTestId('admin-fr-review-dialog');
    await expect(dialog).toContainText(title);
    await expect(dialog).toContainText('신규 장소');
    await expect(dialog).toContainText('장소');
    await expect(dialog).toContainText(`${HAHOE.lon.toFixed(5)}, ${HAHOE.lat.toFixed(5)}`);
    await expect(dialog).toContainText('카페');
    await expect(dialog).toContainText(masked);
    await expect(dialog).toContainText('대기');
    await expect(page.getByTestId('admin-fr-queue-payload-notice')).toContainText('Map Feature 요청 큐에 제출합니다');
    await shot(page, 'ADM-032', 'review-dialog');

    let approveCalls = 0;
    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes(`/admin/feature-requests/${pendingId}/approve`)) approveCalls += 1;
    });
    await page.getByTestId('admin-fr-approve').click();
    await expect(page.locator('#admin-fr-reason-error')).toHaveText('검토 사유를 입력하세요.');
    await expect(page.getByTestId('admin-fr-reason')).toBeFocused();
    await page.waitForTimeout(500);
    expect(approveCalls, 'empty reason must never reach the API').toBe(0);
    await page.getByTestId('admin-fr-review-dialog-close').click();
    await expect(dialog).toHaveCount(0);
    // Still pending in the queue.
    await expect(page.getByTestId(`admin-fr-row-${pendingId}`)).toBeVisible();
  });

  test('ADM-033 an out-of-Map-range (lat > 39.5) proposal never reaches the queue', async () => {
    // Since #614 the shared FeatureRequestCreateSchema refuses new_place lat > 39.5 before any request
    // (packages/schemas/src/feature.ts), so such a suggestion can no longer be created from the UI and
    // the approve-time 422 path (MAP_FEATURE_REQUEST_PAYLOAD_INVALID) is only reachable for legacy rows.
    const title = `${E2E} ADM-033 범위밖 ${tag}`;
    const userPage = user.page;
    let posted = 0;
    const onRequest = (req: { method(): string; url(): string }) => {
      if (req.method() === 'POST' && /\/features\/requests$/.test(new URL(req.url()).pathname)) posted += 1;
    };
    userPage.on('request', onRequest);
    await userPage.goto(`/map?suggest=${OUT_OF_MAP_RANGE.lon},${OUT_OF_MAP_RANGE.lat}`);
    const dialog = userPage.getByTestId('feature-request-dialog');
    await expect(dialog).toBeVisible({ timeout: 30_000 });
    await dialog.getByLabel('이름').fill(title);
    await userPage.getByTestId('feature-request-submit').click();
    await expect(appAlerts(dialog)).toBeVisible({ timeout: 15_000 });
    await userPage.waitForTimeout(1_000);
    userPage.off('request', onRequest);
    expect(posted, 'out-of-range proposal must not be sent').toBe(0);
    await expect(dialog).not.toContainText('제안이 접수됐습니다');
    await shot(userPage, 'ADM-033', 'refused-client-side');
  });

  test('ADM-033b legacy out-of-range row: approve is refused with a clear message (needs a pre-#614 row)', async () => {
    test.skip(!process.env.PINVI_E2E_LEGACY_OUT_OF_RANGE_ID, 'no legacy out-of-range suggestion id provided (cannot be created from the UI since #614)');
    outOfRangeId = process.env.PINVI_E2E_LEGACY_OUT_OF_RANGE_ID!;

    const page = admin.page;
    await openReviewDialog(page, outOfRangeId, 'pending');
    await page.getByTestId('admin-fr-reason').fill(`${E2E} ADM-033 out-of-range approve attempt`);
    const approve = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes(`/admin/feature-requests/${outOfRangeId}/approve`));
    await page.getByTestId('admin-fr-approve').click();
    const res = await approve;
    expect(res.status()).toBe(422);
    const body = (await res.json()) as { error?: { code?: string } };
    expect(body.error?.code).toBe('MAP_FEATURE_REQUEST_PAYLOAD_INVALID');
    const panelError = page.getByTestId('admin-fr-panel-error');
    await expect(panelError).toHaveAttribute('role', 'alert');
    await expect(panelError).toContainText('Map 요청 큐 범위를 벗어난 기존 제안입니다. 거절 후 새 제안으로 접수하세요.');
    await shot(page, 'ADM-033', 'refused');
    await page.getByTestId('admin-fr-review-dialog-close').click();
    const reload = waitForGet(page, /\/admin\/feature-requests/);
    await page.reload();
    await reload;
    await expect(page.getByTestId(`admin-fr-row-${outOfRangeId}`)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId(`admin-fr-row-${outOfRangeId}`)).toContainText('대기');

    // cleanup (terminal reject, no Map call)
    await rejectSuggestionAsAdmin(page, outOfRangeId, `${E2E} cleanup ADM-033 ${tag}`);
    outOfRangeId = '';
  });

  test('ADM-034 reject flow: notice, 거절 tab, user-side status, audit row', async () => {
    test.skip(!pendingId, 'ADM-032 did not run in this selection (it creates the pending suggestion)');
    const reason = `${E2E} ADM-034 reject ${tag}`;
    const page = admin.page;
    await rejectSuggestionAsAdmin(page, pendingId, reason);
    await expect(page.getByTestId('admin-fr-notice')).toBeFocused();

    const rejected = waitForGet(page, /\/admin\/feature-requests\?.*status=rejected/);
    await adminSelect(page, 'admin-fr-status-filter').selectOption('rejected');
    await rejected;
    const row = page.getByTestId(`admin-fr-row-${pendingId}`);
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText('거절');
    await shot(page, 'ADM-034', 'rejected-list');

    // user-side: own request shows rejected
    const origin = await user.apiOrigin();
    const mine = await user.page.request.get(`${origin}/features/requests/${pendingId}`);
    expect(mine.status()).toBe(200);
    const body = (await mine.json()) as { data: { status: string; resolved_at: string | null } };
    expect(body.data.status).toBe('rejected');
    expect(body.data.resolved_at).not.toBeNull();

    // audit log carries the action with our [e2e] reason
    const audit = waitForGet(page, /\/admin\/audit\?limit=100/);
    await page.goto('/admin/audit');
    await audit;
    const auditRow = page.locator('[data-testid^="admin-audit-row-"]').filter({ hasText: 'feature_request.reject' }).filter({ hasText: pendingId });
    await expect(auditRow.first()).toBeVisible({ timeout: 30_000 });
    await expect(auditRow.first()).toContainText(reason);
    const done = pendingId;
    pendingId = '';
    test.info().annotations.push({ type: 'residual', description: `rejected [e2e] suggestion ${done}` });
  });

  test('ADM-035 processed suggestion dialog is read-only', async () => {
    const page = admin.page;
    // The row we just rejected lives under the 거절 filter.
    const rejectedRow = page.locator('[data-testid^="admin-fr-row-"]').filter({ hasText: `${E2E} ADM-032 ${tag}` });
    await page.goto('/admin/feature-requests');
    const list = waitForGet(page, /\/admin\/feature-requests\?.*status=rejected/);
    await adminSelect(page, 'admin-fr-status-filter').selectOption('rejected');
    await list;
    await expect(rejectedRow.first()).toBeVisible({ timeout: 30_000 });
    await rejectedRow.first().getByRole('button', { name: /검토 열기/ }).click();
    const panel = page.getByTestId('admin-fr-review-panel');
    await expect(panel).toContainText('처리 완료된 제안입니다.');
    await expect(page.getByTestId('admin-fr-approve')).toHaveCount(0);
    await expect(page.getByTestId('admin-fr-reject')).toHaveCount(0);
    await page.getByTestId('admin-fr-review-dialog-close').click();
  });
});

test.describe('ADM-036 promotion review on mobile', () => {
  test('ADM-036 mobile card → review dialog → close restores focus; then cleanup reject', async ({ browser }) => {
    test.skip(!isMobileProject(), 'mobile project only');
    test.skip(gated(), 'set PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS=1 to accept residual rejected [e2e] suggestion rows');
    const tag = runTag();
    const viewport = { width: 390, height: 844 };
    const user = await newUserActor(browser, viewport);
    const admin = await newAdminActor(browser, viewport);
    let id = '';
    try {
      id = await createE2eSuggestion(user, { ...HAHOE, title: `${E2E} ADM-036 ${tag}` });
      const page = admin.page;
      const list = waitForGet(page, /\/admin\/feature-requests/);
      await page.goto('/admin/feature-requests');
      await list;
      const card = page.getByTestId(`admin-fr-mobile-card-${id}`);
      await expect(card).toBeVisible({ timeout: 30_000 });
      await expect(card).toContainText('신규 장소');
      await expect(card).toContainText(maskedEmail(requireEnv('PINVI_E2E_USER_EMAIL')));
      const review = page.getByTestId(`admin-fr-mobile-review-${id}`);
      const box = await review.boundingBox();
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
      await review.click();
      await expect(page.getByTestId('admin-fr-review-dialog')).toBeVisible();
      await shot(page, 'ADM-036', 'mobile-dialog');
      await page.getByTestId('admin-fr-review-dialog-close').click();
      await expect(page.getByTestId('admin-fr-review-dialog')).toHaveCount(0);
      await expect(review).toBeFocused();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    } finally {
      if (id) await rejectSuggestionAsAdmin(admin.page, id, `${E2E} cleanup ADM-036 ${tag}`).catch(() => undefined);
      await user.context.close();
      await admin.context.close();
    }
  });
});
