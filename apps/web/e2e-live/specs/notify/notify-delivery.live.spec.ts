/**
 * NTF — 실제 전송 (trip_created outbox → drain worker → Telegram sendMessage) 및 미연결 시 skip.
 * Cases: NTF-012, NTF-014.
 *
 * Delivery evidence WITHOUT reading any chat:
 *   1. target row status on /settings/telegram ('정상' = last_send_status ok, or 'failed:<code>')
 *   2. admin /admin/api-calls provider=telegram → `…/bot<id>:*** /sendMessage` HTTP 200 row
 *      whose occurred_at ≥ trip creation time (apps/api/app/middleware/api_call_logging.py)
 *   3. admin /admin/etl Telegram outbox card category `trip_created` present (shape only)
 * Message BODY assertions need a chat reader → NTF-013 (blocked, see README).
 *
 * Flow facts: apps/api/app/api/v1/trips.py:399-411 enqueues category trip_created on POST /trips;
 * telegram_outbox._drain_loop every 5s; telegram_notify.deliver_user_notification picks the
 * default (else newest enabled) target and sends plain text.
 */
import { expect, test, type Browser, type Page } from '@playwright/test';
import { appAlerts, baseURL, createTrip, deleteTrip, loginAsAdmin, loginAsUser, shot } from '../../helpers/live';
import {
  e2eLabel,
  isMobileProject,
  isoDateFromToday,
  listTargets,
  registerTargetViaForm,
  requireTestChat,
  resolveApiBase,
  sweepE2eTargets,
  targetRow,
  tripTitle,
  waitForTelegramSendSince,
  skipIfRealDefaultTarget,
} from '../../helpers/notify';

async function adminPage(browser: Browser): Promise<Page> {
  const ctx = await browser.newContext({ baseURL });
  const page = await ctx.newPage();
  await loginAsAdmin(page);
  return page;
}

test.describe('NTF delivery — trip_created 알림', () => {
  let apiBase = '';
  let tripId: string | null = null;

  test.beforeEach(async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only (admin evidence pages)');
    await loginAsUser(page);
    apiBase = await resolveApiBase(page);
    await sweepE2eTargets(page, apiBase);
  });

  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
    await sweepE2eTargets(page, apiBase).catch(() => undefined);
  });

  test('NTF-012 기본 대상=테스트 chat → 여행 생성 → sendMessage 200 (admin 로그) + 대상 상태 정상', async ({ page, browser }) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-012');
    await skipIfRealDefaultTarget(test, page, apiBase);
    await page.goto('/settings/telegram');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: true });
    expect(created.status).toBe(201);
    test.skip(!created.data?.last_verified_at, 'prod bot token unset → delivery is skipped by design; blocked');

    const start = isoDateFromToday(30);
    const end = isoDateFromToday(32);
    const sinceIso = new Date(Date.now() - 2_000).toISOString(); // small skew allowance
    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-012'), start, end, region: '부산' }));
    // In-app feedback of the action that enqueues the notification.
    await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();
    await shot(page, 'NTF-012', 'trip-created-toast');

    // Admin evidence: Telegram API accepted a sendMessage after creation.
    const admin = await adminPage(browser);
    try {
      const row = await waitForTelegramSendSince(admin, sinceIso, { timeoutMs: 60_000 });
      expect(row.endpoint).toMatch(/\/bot\d+:\*\*\*\/sendMessage$/); // token masked
      expect(row.endpoint).not.toMatch(/\/bot\d+:[A-Za-z0-9_-]{20,}/);
      await shot(admin, 'NTF-012', 'admin-api-calls');
    } finally {
      await admin.context().close();
    }

    // User-side evidence: last_send_status=ok rendered as '정상', target still enabled.
    await page.goto('/settings/telegram');
    await expect(targetRow(page, label)).toContainText('정상');
    const after = (await listTargets(page, apiBase)).find((t) => t.id === created.data!.id);
    expect(after?.last_send_status).toBe('ok');
    expect(after?.is_enabled).toBe(true);
    await shot(page, 'NTF-012', 'target-ok');
  });

  test('NTF-014 대상 미연결 상태에서 여행 생성 → UI 정상, 알림은 skipped, Telegram 호출 없음', async ({ page, browser }) => {
    const existing = await listTargets(page, apiBase);
    test.skip(existing.length > 0, '테스트 계정에 실(非 e2e) Telegram 대상이 있어 "미연결" 전제가 성립하지 않음');

    const sinceIso = new Date(Date.now() - 2_000).toISOString();
    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-014'), start: isoDateFromToday(30), end: isoDateFromToday(31) }));
    await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();
    await expect(appAlerts(page)).toHaveCount(0);

    const admin = await adminPage(browser);
    try {
      // Give the drain worker two full intervals, then assert no sendMessage row since creation.
      await admin.waitForTimeout(12_000);
      await expect(waitForTelegramSendSince(admin, sinceIso, { timeoutMs: 1 })).rejects.toThrow(/not found/);
      // Outbox summary still reports the category (shape, not count — other users create trips too).
      const [summary] = await Promise.all([
        admin.waitForResponse((r) => r.url().includes('/admin/etl/summary')),
        admin.goto('/admin/etl'),
      ]);
      const body = (await summary.json()) as { data: { pinvi: { telegram_outbox: { category_stats: { category: string; skipped: number }[] } | null } } };
      const stats = body.data.pinvi.telegram_outbox?.category_stats ?? [];
      const tc = stats.find((s) => s.category === 'trip_created');
      expect(tc, 'trip_created category must exist in the 24h window').toBeTruthy();
      expect(tc!.skipped).toBeGreaterThanOrEqual(1);
      await expect(admin.getByTestId('admin-etl-telegram-category-trip_created')).toBeVisible();
      await shot(admin, 'NTF-014', 'admin-etl-outbox');
    } finally {
      await admin.context().close();
    }
  });
});
