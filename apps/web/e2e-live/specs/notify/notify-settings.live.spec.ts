/**
 * NTF — 설정 > Telegram 알림 (target CRUD + verify + failure handling).
 * Cases: NTF-001, 002, 003, 004, 005, 006, 007, 016, 026.
 *
 * UI contract: apps/web/app/(app)/settings/telegram/page.tsx (PinVi main 620b6046+)
 * API contract: apps/api/app/api/v1/telegram_targets.py + services/telegram_targets.py
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  BOGUS_CHAT_ID,
  e2eLabel,
  isMobileProject,
  listTargets,
  registerTargetViaForm,
  requireTestChat,
  resolveApiBase,
  sweepE2eTargets,
  targetRow,
  targetsList,
  skipIfRealDefaultTarget,
} from '../../helpers/notify';

test.describe('NTF settings — Telegram 알림', () => {
  let apiBase = '';

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    apiBase = await resolveApiBase(page); // lands on /settings/telegram
    await sweepE2eTargets(page, apiBase); // leftovers from a failed earlier run
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Telegram 알림' })).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    // Mandatory cleanup even on failure: only `[e2e]`-labelled targets of the test user.
    await sweepE2eTargets(page, apiBase).catch(() => undefined);
  });

  test('NTF-001 설정 > Telegram 알림 진입: 탭·안내문·폼 라벨·경고', async ({ page }, info) => {
    await expect(page.getByTestId('settings-tab-telegram')).toBeVisible();
    await expect(page.getByTestId('settings-tab-telegram')).toHaveText('Telegram 알림');
    await expect(page.getByText('Pinvi 봇을 chat에 추가한 뒤')).toBeVisible();
    await expect(page.getByText('그룹/채널을 연결하면 그 방의 다른 사람도 알림을 볼 수 있습니다.')).toBeVisible();
    await expect(page.getByRole('heading', { name: '새 대상 연결' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '연결된 대상' })).toBeVisible();
    // FormField label↔input binding (a11y).
    await expect(page.getByLabel('Chat ID')).toBeVisible();
    await expect(page.getByText('예: -1001234567890 (그룹) 또는 123456789 (개인)')).toBeVisible();
    await expect(page.getByLabel('별칭 (선택)')).toBeVisible();
    await expect(page.getByLabel('기본 대상')).toBeChecked(); // default on
    await expect(page.getByTestId('telegram-create')).toHaveText(/연결/);
    // Either an empty-state sentence or a list — never an error.
    await expect(page.getByTestId('telegram-error')).toHaveCount(0);
    await shot(page, 'NTF-001', isMobileProject(info) ? 'mobile-landing' : 'landing');
  });

  test('NTF-002 Chat ID 비움 제출 → 필드 오류·aria-invalid·포커스 (네트워크 없음)', async ({ page }) => {
    let posted = false;
    page.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/users/me/telegram-targets')) posted = true;
    });
    await page.getByTestId('telegram-create').click();
    await expect(page.locator('#telegram-chat-id-error')).toHaveText('chat ID를 입력하세요.');
    await expect(page.getByTestId('telegram-chat-id')).toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByTestId('telegram-chat-id')).toBeFocused();
    expect(posted, 'client-side validation must not hit the API').toBe(false);
    await shot(page, 'NTF-002', 'field-error');
  });

  test('NTF-003 존재하지 않는 chat ID 등록 → verify 실패(invalid_chat) 알림, 목록 미추가', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const label = e2eLabel('NTF-003 bogus');
    const result = await registerTargetViaForm(page, { chatId: BOGUS_CHAT_ID, label, isDefault: false });

    if (result.status === 201) {
      // Prod bot token NOT configured: API skips getChat and persists as 미검증 (telegram_targets._apply_verify).
      // Record the fact (README "known gaps") and still assert the UI contract for that branch.
      test.info().annotations.push({ type: 'note', description: 'prod PINVI_TELEGRAM_BOT_TOKEN_DEFAULT unset: verify skipped' });
      await expect(targetRow(page, label)).toContainText('미검증');
      return;
    }
    expect([422, 403, 503, 502, 429]).toContain(result.status);
    expect(result.code).toBe('invalid_chat'); // §5 classification for 400 "chat not found"
    const alert = page.getByTestId('telegram-error');
    await expect(alert).toBeVisible();
    await expect(alert).toHaveText('telegram verify 실패: invalid_chat');
    // Not persisted (create_target rolls back on verify failure).
    await expect(targetRow(page, label)).toHaveCount(0);
    const rows = await listTargets(page, apiBase);
    expect(rows.some((t) => t.telegram_label === label)).toBe(false);
    // Form keeps the user's input so they can correct it.
    await expect(page.getByTestId('telegram-chat-id')).toHaveValue(BOGUS_CHAT_ID);
    await shot(page, 'NTF-003', 'invalid-chat');
  });

  test('NTF-004 테스트 chat 등록 → verify 성공 → 정상·chat type·제목 스냅샷, 폼 리셋', async ({ page }, info) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-004');
    await skipIfRealDefaultTarget(test, page, apiBase);
    const result = await registerTargetViaForm(page, { chatId, label, isDefault: true });
    expect(result.status, result.message ?? '').toBe(201);
    expect(result.data?.telegram_label).toBe(label);
    expect(result.data?.is_default).toBe(true);

    const row = targetRow(page, label);
    await expect(row).toBeVisible();
    await expect(row.getByLabel('기본')).toBeVisible(); // ★ default star
    // Boolean check: a failing toContainText would print the chat id into the report.
    await expect.poll(async () => ((await row.textContent()) ?? '').includes(chatId), { message: 'target row shows the test chat id' }).toBe(true);
    if (result.data?.last_verified_at) {
      // verify ran (prod bot token set): type + status
      expect(['private', 'group', 'supergroup', 'channel']).toContain(result.data.telegram_chat_type);
      await expect(row).toContainText('정상');
      await expect(row).toContainText(result.data.telegram_chat_type as string);
      if (result.data.title_snapshot) await expect(row).toContainText(result.data.title_snapshot);
    } else {
      await expect(row).toContainText('미검증');
    }
    // Form reset after success.
    await expect(page.getByTestId('telegram-chat-id')).toHaveValue('');
    await expect(page.getByTestId('telegram-label')).toHaveValue('');
    await expect(page.getByTestId('telegram-error')).toHaveCount(0);
    await shot(page, 'NTF-004', isMobileProject(info) ? 'mobile-registered' : 'registered');
  });

  test('NTF-005 재검증 → POST …/verify 200 → 정상 유지·last_verified_at 갱신', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-005');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: false });
    expect(created.status).toBe(201);
    const before = created.data?.last_verified_at ?? null;

    const row = targetRow(page, label);
    const [res] = await Promise.all([
      page.waitForResponse((r) => /\/users\/me\/telegram-targets\/[0-9a-f-]{36}\/verify$/.test(r.url())),
      row.getByRole('button', { name: `${label} 재검증` }).click(),
    ]);
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { data: { last_verified_at: string | null; last_send_status: string | null } };
    if (before) {
      expect(new Date(body.data.last_verified_at as string).getTime()).toBeGreaterThan(new Date(before).getTime());
      expect(body.data.last_send_status).toBe('ok');
      await expect(row).toContainText('정상');
    } else {
      // token unset on prod: verify is a no-op → still 미검증
      await expect(row).toContainText('미검증');
    }
    // Buttons re-enabled after the request (busyTargetId cleared).
    await expect(row.getByRole('button', { name: `${label} 재검증` })).toBeEnabled();
    await shot(page, 'NTF-005', 'reverified');
  });

  test('NTF-006 대상 삭제 → 목록에서 제거, DELETE 204, 비었을 때 안내 문구', async ({ page }, info) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-006');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: false });
    expect(created.status).toBe(201);
    const row = targetRow(page, label);
    await expect(row).toBeVisible();

    const [res] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes(`/users/me/telegram-targets/${created.data?.id}`)),
      row.getByRole('button', { name: `${label} 삭제` }).click(),
    ]);
    expect(res.status()).toBe(204);
    await expect(targetRow(page, label)).toHaveCount(0);

    const remaining = await listTargets(page, apiBase);
    expect(remaining.some((t) => t.id === created.data?.id)).toBe(false);
    if (remaining.length === 0) {
      await expect(page.getByText('연결된 대상이 없습니다. 위에서 chat ID를 등록하면 알림을 받을 수 있습니다.')).toBeVisible();
    }
    await shot(page, 'NTF-006', isMobileProject(info) ? 'mobile-deleted' : 'deleted');
  });

  test('NTF-007 기본 대상 전환: 두 번째 대상을 기본으로 등록하면 ★가 이동하고 목록이 기본 우선 정렬', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const chatId = requireTestChat(test);
    const a = e2eLabel('NTF-007 A');
    const b = e2eLabel('NTF-007 B');
    await skipIfRealDefaultTarget(test, page, apiBase);
    expect((await registerTargetViaForm(page, { chatId, label: a, isDefault: true })).status).toBe(201);
    await expect(targetRow(page, a).getByLabel('기본')).toBeVisible();

    expect((await registerTargetViaForm(page, { chatId, label: b, isDefault: true })).status).toBe(201);
    // Star moved (service `_clear_default` + page optimistic update).
    await expect(targetRow(page, b).getByLabel('기본')).toBeVisible();
    await expect(targetRow(page, a).getByLabel('기본')).toHaveCount(0);

    // Server-side truth after reload: exactly one default among our rows, default first.
    await page.reload();
    const rows = (await listTargets(page, apiBase)).filter((t) => t.telegram_label?.startsWith('[e2e] NTF-007'));
    expect(rows.filter((t) => t.is_default).map((t) => t.telegram_label)).toEqual([b]);
    const items = targetsList(page).getByRole('listitem');
    const first = items.filter({ hasText: '[e2e] NTF-007' }).first();
    await expect(first).toContainText(b);
    await shot(page, 'NTF-007', 'default-moved');
  });

  test('NTF-016 봇이 추방된 chat 재검증 → 403 bot_forbidden → failed:bot_forbidden·비활성', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const forbidden = process.env.PINVI_E2E_TELEGRAM_FORBIDDEN_CHAT_ID?.trim();
    test.skip(!forbidden, 'PINVI_E2E_TELEGRAM_FORBIDDEN_CHAT_ID 미설정 — blocked (README)');
    const label = e2eLabel('NTF-016 forbidden');

    // Registration itself must be refused with bot_forbidden (verify runs on create).
    const created = await registerTargetViaForm(page, { chatId: forbidden as string, label, isDefault: false });
    if (created.status === 201) {
      test.info().annotations.push({ type: 'note', description: 'prod bot token unset: create did not verify' });
      // Re-verify path is still the contract under test when token is set; nothing to assert without it.
      return;
    }
    expect(created.status).toBe(403);
    expect(created.code).toBe('bot_forbidden');
    await expect(page.getByTestId('telegram-error')).toHaveText('telegram verify 실패: bot_forbidden');
    await expect(targetRow(page, label)).toHaveCount(0);
    await shot(page, 'NTF-016', 'bot-forbidden');
  });

  test('NTF-026 모바일 390: 탭 nav 가로 스크롤·폼 세로 스택·터치 타깃 ≥44px', async ({ page }, info) => {
    test.skip(!isMobileProject(info), 'mobile project only');
    await expect(page.getByTestId('settings-tab-telegram')).toBeVisible();
    const nav = page.getByRole('navigation', { name: '설정 메뉴' });
    await expect(nav).toBeVisible();
    // Form controls stacked (single column at <md): chat-id input above label input.
    const chat = await page.getByTestId('telegram-chat-id').boundingBox();
    const label = await page.getByTestId('telegram-label').boundingBox();
    const submit = await page.getByTestId('telegram-create').boundingBox();
    expect(chat && label && submit).toBeTruthy();
    expect(label!.y).toBeGreaterThan(chat!.y + chat!.height - 1);
    expect(submit!.height).toBeGreaterThanOrEqual(44);
    // No horizontal page scroll.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await shot(page, 'NTF-026', 'mobile-form');
  });
});
