import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const targetA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const targetB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function target(id: string, label: string, chatId: string, isDefault = false) {
  return {
    id,
    telegram_chat_id: chatId,
    telegram_chat_type: 'group',
    telegram_message_thread_id: null,
    telegram_label: label,
    title_snapshot: null,
    is_default: isDefault,
    is_enabled: true,
    last_verified_at: '2026-06-10T09:00:00+09:00',
    last_send_status: 'ok',
    created_at: '2026-06-10T09:00:00+09:00',
  };
}

const TRIP_VIEW = {
  trip: {
    trip_id: tripId,
    owner_user_id: userId,
    title: '부산 2박 3일',
    description: null,
    region_hint: '부산',
    primary_region_code: null,
    primary_region_source: null,
    start_date: '2026-07-01',
    end_date: '2026-07-03',
    visibility: 'private',
    status: 'planned',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  },
  days: [],
  companions: [],
  share_links: [],
  broken_feature_count: 0,
};

test('trip 상세에서 Telegram 대상을 연결하고 해제한다', async ({ page }) => {
  const linked: string[] = [targetA];
  const ALL = [target(targetA, '가족 단톡', '-100111', true), target(targetB, '친구방', '-100222')];

  await page.route(/.*\/auth\/me$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: { user_id: userId } }) });
  });
  for (const sub of ['comments', 'attachments']) {
    await page.route(new RegExp(`.*/trips/[0-9a-f-]{36}/${sub}(\\?.*)?$`), async (route, request) => {
      if (!isFetch(request.resourceType())) return route.continue();
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
    });
  }
  await page.route(/.*\/users\/me\/telegram-targets$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: ALL }) });
  });
  // trip-link 목록/연결/해제 (stateful).
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/telegram-targets$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'POST') {
      const body = JSON.parse(request.postData() ?? '{}');
      linked.push(body.telegram_target_id);
      const t = ALL.find((x) => x.id === body.telegram_target_id);
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ data: t }) });
      return;
    }
    const rows = ALL.filter((t) => linked.includes(t.id));
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: rows }) });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/telegram-targets\/[0-9a-f-]{36}$/, async (route, request) => {
    if (request.method() !== 'DELETE') return route.continue();
    const id = request.url().split('/').pop() ?? '';
    const idx = linked.indexOf(id);
    if (idx >= 0) linked.splice(idx, 1);
    await route.fulfill({ status: 204, body: '' });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: TRIP_VIEW }) });
  });

  await page.goto(`/trips/${tripId}`);

  const section = page.getByTestId('trip-telegram-targets');
  await expect(section.getByRole('heading', { name: 'Telegram 알림 대상' })).toBeVisible();
  // 초기: A 연결됨.
  await expect(page.getByTestId('trip-telegram-list')).toContainText('가족 단톡');

  // B 연결.
  await page.getByTestId('trip-telegram-select').selectOption(targetB);
  await page.getByTestId('trip-telegram-link').click();
  await expect(page.getByTestId('trip-telegram-list')).toContainText('친구방');

  // A 해제.
  await page.getByTestId('trip-telegram-unlink--100111').click();
  await expect(page.getByTestId('trip-telegram-list')).not.toContainText('가족 단톡');
  await expect(page.getByTestId('trip-telegram-list')).toContainText('친구방');
});
