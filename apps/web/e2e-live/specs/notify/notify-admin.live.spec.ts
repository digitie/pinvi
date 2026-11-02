/**
 * NTF — admin read-only surfaces for notifications.
 * Cases: NTF-022 (이메일 큐), NTF-023 (ETL 요약 Telegram outbox 카드), NTF-024 (API 호출 로그 토큰 마스킹).
 *
 * UI: apps/web/app/(admin)/admin/emails/page.tsx, admin/etl/page.tsx, admin/api-calls/page.tsx
 */
import { expect, test } from '@playwright/test';
import { loginAsAdmin, shot } from '../../helpers/live';
import { adminTelegramCalls, isMobileProject } from '../../helpers/notify';

test.describe('NTF admin — 알림 운영 화면 (read-only)', () => {
  test.beforeEach(async ({ page }, info) => {
    test.skip(isMobileProject(info), 'admin surfaces are desktop-only in this area');
    await loginAsAdmin(page);
  });

  test('NTF-022 /admin/emails 이메일 큐 smoke: 제목·deliverability 카드·상태 필터', async ({ page }) => {
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/admin/emails/deliverability')),
      page.goto('/admin/emails'),
    ]);
    expect(res.ok()).toBeTruthy();
    await expect(page.getByRole('heading', { name: '이메일 큐' })).toBeVisible();
    await expect(page.getByTestId('admin-email-deliverability')).toBeVisible();
    await expect(page.getByTestId('admin-email-deliverability-status')).not.toHaveText('');
    await expect(page.getByTestId('admin-emails-status-filter')).toBeVisible();
    await expect(page.getByTestId('admin-emails-refresh')).toBeEnabled();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await shot(page, 'NTF-022', 'emails');
  });

  test('NTF-023 /admin/etl Telegram outbox 카드: due/backoff/stuck/retry exhausted 숫자 + 임계값', async ({ page }) => {
    const [res] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/admin/etl/summary')),
      page.goto('/admin/etl'),
    ]);
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()) as {
      data: { pinvi: { telegram_outbox: null | { pending_due: number; stuck_pending: number; max_attempts: number; stuck_threshold_minutes: number; category_window_hours: number; category_stats: { category: string }[] } } };
    };
    const tg = body.data.pinvi.telegram_outbox;
    expect(tg, 'telegram_outbox summary must be present').toBeTruthy();
    expect(tg!.max_attempts).toBe(5); // telegram_outbox.MAX_TELEGRAM_ATTEMPTS
    const card = page.getByTestId('admin-etl-telegram-outbox');
    await expect(card).toBeVisible();
    await expect(card).toContainText('Telegram outbox');
    for (const k of ['due', 'backoff', 'stuck', 'retry exhausted', 'sent', 'skipped', 'failed']) {
      await expect(card).toContainText(k);
    }
    await expect(card).toContainText(`threshold ${tg!.stuck_threshold_minutes}m / max attempts ${tg!.max_attempts} / ${tg!.category_window_hours}h categories`);
    await expect(page.getByTestId('admin-etl-telegram-stuck')).toContainText(String(tg!.stuck_pending));
    for (const s of tg!.category_stats) {
      await expect(page.getByTestId(`admin-etl-telegram-category-${s.category}`)).toBeVisible();
    }
    // Operational signal, not a hard gate: stuck pending should be 0 in a healthy prod.
    test.info().annotations.push({ type: 'telegram_outbox.stuck_pending', description: String(tg!.stuck_pending) });
    await shot(page, 'NTF-023', 'etl-telegram-outbox');
  });

  test('NTF-024 /admin/api-calls provider=telegram: 봇 토큰이 항상 /bot<id>:***/ 로 마스킹', async ({ page }) => {
    const rows = await adminTelegramCalls(page);
    // Rows exist once anyone registered/verified a target or a notification was sent.
    test.skip(rows.length === 0, 'api_call_log에 provider=telegram 행이 아직 없음 — NTF-004 이후 재실행');
    for (const r of rows) {
      expect(r.provider).toBe('telegram');
      expect(r.endpoint).toMatch(/^https:\/\/api\.telegram\.org\/bot\d+:\*\*\*\/(getChat|sendMessage)/);
      expect(r.endpoint).not.toMatch(/\/bot\d+:[A-Za-z0-9_-]{20,}/);
    }
    // Rendered table shows the masked endpoint too.
    await expect(page.getByText(/\/bot\d+:\*\*\*\/(getChat|sendMessage)/).first()).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await shot(page, 'NTF-024', 'api-calls-telegram');
  });
});
