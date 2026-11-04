/**
 * NTF — 여행 상세 '공유' 탭 > Telegram 알림 대상 (trip ↔ target link).
 * Cases: NTF-008, 009, 010, 011.
 *
 * UI: apps/web/components/trips/TripTelegramTargets.tsx (rendered inside TripDetail.tsx
 *     tab id 'share' label '공유', line ~1239/1877)
 * API: apps/api/app/api/v1/trip_telegram_targets.py (≤3 per trip → 422 MAX_TARGETS_REACHED)
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, openTripTab, shot } from '../../helpers/live';
import {
  e2eLabel,
  isMobileProject,
  isoDateFromToday,
  listTargets,
  registerTargetViaForm,
  requireTestChat,
  resolveApiBase,
  sweepE2eTargets,
  tripTitle,
  skipIfRealDefaultTarget,
} from '../../helpers/notify';

const section = (page: import('@playwright/test').Page) => page.getByTestId('trip-telegram-targets');

async function openShareTab(page: import('@playwright/test').Page, tripId: string) {
  await page.goto(`/trips/${tripId}`);
  await openTripTab(page, '공유'); // opens the mobile drawer when needed
  await expect(section(page).getByRole('heading', { name: 'Telegram 알림 대상' })).toBeVisible();
  // Section finished loading (both list calls resolved).
  await expect(section(page).getByText('불러오는 중…')).toHaveCount(0);
}

test.describe('NTF trip link — 공유 탭 Telegram 알림 대상', () => {
  let apiBase = '';
  let tripId: string | null = null;

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    apiBase = await resolveApiBase(page);
    await sweepE2eTargets(page, apiBase);
  });

  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
    await sweepE2eTargets(page, apiBase).catch(() => undefined);
  });

  test('NTF-008 대상이 없으면 안내 문구 + 설정 링크, 대상이 있으면 선택 셀렉트', async ({ page }, info) => {
    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-008'), start: isoDateFromToday(20), end: isoDateFromToday(22) }));
    const existing = await listTargets(page, apiBase); // real (non-e2e) targets of the test user, if any
    await openShareTab(page, tripId);

    await expect(section(page)).toContainText('이 여행의 알림을 받을 대상을 연결합니다(최대 3개)');
    const link = section(page).getByRole('link', { name: '설정 > Telegram 알림' });
    await expect(link).toHaveAttribute('href', '/settings/telegram');
    if (existing.length === 0) {
      await expect(section(page).getByText('등록된 Telegram 대상이 없습니다. 먼저 설정에서 대상을 등록하세요.')).toBeVisible();
      await expect(page.getByTestId('trip-telegram-select')).toHaveCount(0);
    } else {
      await expect(page.getByTestId('trip-telegram-select')).toBeVisible();
      await expect(page.getByTestId('trip-telegram-select')).toContainText('선택하세요');
    }
    await expect(page.getByTestId('trip-telegram-list')).toHaveCount(0); // nothing linked on a fresh trip
    await expect(page.getByTestId('trip-telegram-error')).toHaveCount(0);
    await shot(page, 'NTF-008', isMobileProject(info) ? 'mobile-share-tab' : 'share-tab');
  });

  test('NTF-009 여행에 대상 연결 → 목록 표시 → 해제 → 목록에서 제거', async ({ page }, info) => {
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-009');
    await skipIfRealDefaultTarget(test, page, apiBase);
    await page.goto('/settings/telegram');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: true });
    expect(created.status).toBe(201);

    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-009'), start: isoDateFromToday(20), end: isoDateFromToday(22) }));
    await openShareTab(page, tripId);

    await page.getByTestId('trip-telegram-select').selectOption(created.data!.id);
    const [linkRes] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/trips/${tripId}/telegram-targets`)),
      page.getByTestId('trip-telegram-link').click(),
    ]);
    expect(linkRes.status()).toBe(201);
    const list = page.getByTestId('trip-telegram-list');
    await expect(list).toContainText(label);
    // Boolean check: a failing toContainText would print the chat id into the report.
    await expect.poll(async () => ((await list.textContent()) ?? '').includes(chatId), { message: 'linked target shows the test chat id' }).toBe(true);
    await expect(list.getByLabel('기본')).toBeVisible();
    // The linked target disappears from the selectable options.
    await expect(page.getByTestId('trip-telegram-select').locator(`option[value="${created.data!.id}"]`)).toHaveCount(0);
    await shot(page, 'NTF-009', isMobileProject(info) ? 'mobile-linked' : 'linked');

    const [unlinkRes] = await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().endsWith(`/trips/${tripId}/telegram-targets/${created.data!.id}`)),
      list.getByRole('button', { name: `${label} 연결 해제` }).click(),
    ]);
    expect(unlinkRes.status()).toBe(204);
    await expect(page.getByTestId('trip-telegram-list')).toHaveCount(0);
    await expect(page.getByTestId('trip-telegram-select').locator(`option[value="${created.data!.id}"]`)).toHaveCount(1);
    await shot(page, 'NTF-009', 'unlinked');
  });

  test('NTF-010 여행당 최대 3개: 3개 연결 후 셀렉트 비활성·"최대 3개 연결됨"', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const chatId = requireTestChat(test);
    await page.goto('/settings/telegram');
    const ids: string[] = [];
    for (const n of [1, 2, 3, 4]) {
      const r = await registerTargetViaForm(page, { chatId, label: e2eLabel(`NTF-010 #${n}`), isDefault: false });
      expect(r.status).toBe(201);
      ids.push(r.data!.id);
    }
    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-010'), start: isoDateFromToday(20), end: isoDateFromToday(21) }));
    await openShareTab(page, tripId);

    for (const id of ids.slice(0, 3)) {
      await page.getByTestId('trip-telegram-select').selectOption(id);
      await Promise.all([
        page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/trips/${tripId}/telegram-targets`) && r.status() === 201),
        page.getByTestId('trip-telegram-link').click(),
      ]);
    }
    await expect(page.getByTestId('trip-telegram-list').getByRole('listitem')).toHaveCount(3);
    await expect(section(page).getByText('최대 3개 연결됨')).toBeVisible();
    await expect(page.getByTestId('trip-telegram-select')).toBeDisabled();
    await expect(page.getByTestId('trip-telegram-link')).toBeDisabled();
    await shot(page, 'NTF-010', 'at-limit');

    // Server-side guard independent of the UI: 4th link → 422 MAX_TARGETS_REACHED.
    const res = await page.request.post(`${apiBase}/trips/${tripId}/telegram-targets`, { data: { telegram_target_id: ids[3] } });
    expect(res.status()).toBe(422);
    const body = (await res.json()) as { detail?: { code?: string; reason?: string }; code?: string };
    expect(body.detail?.code ?? body.code).toBe('MAX_TARGETS_REACHED');
  });

  test('NTF-011 설정에서 대상을 삭제하면 여행의 연결 목록에서도 사라진다', async ({ page }, info) => {
    test.skip(isMobileProject(info), 'desktop only');
    const chatId = requireTestChat(test);
    const label = e2eLabel('NTF-011');
    await page.goto('/settings/telegram');
    const created = await registerTargetViaForm(page, { chatId, label, isDefault: false });
    expect(created.status).toBe(201);
    ({ id: tripId } = await createTrip(page, { title: tripTitle('NTF-011'), start: isoDateFromToday(20), end: isoDateFromToday(21) }));
    await openShareTab(page, tripId);
    await page.getByTestId('trip-telegram-select').selectOption(created.data!.id);
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/trips/${tripId}/telegram-targets`) && r.status() === 201),
      page.getByTestId('trip-telegram-link').click(),
    ]);
    await expect(page.getByTestId('trip-telegram-list')).toContainText(label);

    // Soft-delete in settings (deleted_at set) → list_trip_targets filters it out.
    await page.goto('/settings/telegram');
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes(`/users/me/telegram-targets/${created.data!.id}`)),
      page.getByRole('list', { name: '연결된 Telegram 대상' }).getByRole('listitem').filter({ hasText: label }).getByRole('button', { name: `${label} 삭제` }).click(),
    ]);
    await openShareTab(page, tripId);
    await expect(page.getByTestId('trip-telegram-list')).toHaveCount(0);
    await expect(page.getByTestId('trip-telegram-error')).toHaveCount(0);
    await shot(page, 'NTF-011', 'after-target-delete');
  });
});
