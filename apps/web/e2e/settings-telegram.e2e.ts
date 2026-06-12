import { expect, test } from '@playwright/test';

const targetId = '99999999-9999-4999-8999-999999999999';

function targetBody(overrides: Record<string, unknown> = {}) {
  return {
    id: targetId,
    telegram_chat_id: '-1001234',
    telegram_chat_type: 'group',
    telegram_message_thread_id: null,
    telegram_label: '가족 단톡',
    title_snapshot: '가족 단톡방',
    is_default: true,
    is_enabled: true,
    last_verified_at: '2026-06-10T09:00:00+09:00',
    last_send_status: 'ok',
    created_at: '2026-06-10T09:00:00+09:00',
    ...overrides,
  };
}

test('Telegram 대상 등록 → 목록 반영 → 삭제', async ({ page }) => {
  const targets: Array<Record<string, unknown>> = [];

  await page.route(
    (url) => url.port === '12501' && url.pathname === '/users/me/telegram-targets',
    async (route, request) => {
      if (request.method() === 'POST') {
        targets.unshift(targetBody());
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ data: targetBody() }),
        });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: targets }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12501' && url.pathname === `/users/me/telegram-targets/${targetId}`,
    async (route, request) => {
      if (request.method() !== 'DELETE') return route.continue();
      targets.length = 0;
      await route.fulfill({ status: 204, body: '' });
    },
  );

  await page.goto('/settings/telegram');
  await expect(page.getByRole('heading', { name: 'Telegram 알림' })).toBeVisible();
  // settings 서브내비에 탭 노출.
  await expect(page.getByTestId('settings-tab-telegram')).toBeVisible();

  // label↔input 연결(접근성) — FormField.
  await expect(page.getByLabel('Chat ID')).toBeVisible();

  await page.getByTestId('telegram-chat-id').fill('-1001234');
  await page.getByTestId('telegram-label').fill('가족 단톡');
  await page.getByTestId('telegram-create').click();

  const list = page.getByTestId('telegram-chat-id');
  await expect(page.getByText('가족 단톡방')).toBeVisible(); // verify 스냅샷 표시
  await expect(list).toHaveValue(''); // 폼 리셋

  await page.getByTestId('telegram-delete--1001234').click();
  await expect(page.getByText('가족 단톡방')).toBeHidden();
});

test('Chat ID 없이 연결하면 필드 오류 + aria-invalid + 포커스', async ({ page }) => {
  await page.route(
    (url) => url.port === '12501' && url.pathname === '/users/me/telegram-targets',
    async (route, request) => {
      if (request.method() !== 'GET') return route.continue();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    },
  );

  await page.goto('/settings/telegram');
  await page.getByTestId('telegram-create').click();

  const err = page.locator('#telegram-chat-id-error');
  await expect(err).toBeVisible();
  await expect(page.getByTestId('telegram-chat-id')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('telegram-chat-id')).toBeFocused();
});
