/**
 * TRIP-056 … TRIP-057 — second ordinary user `test2@test.com` (PINVI_E2E_USER2_EMAIL/PASSWORD).
 * 056: dashboard empty state (user2 is expected to own no trips; sweeps its own `[e2e]` trips and
 *      skips if anything else is there — never deletes non-prefixed data).
 * 057: identity isolation — user2 cannot open user1's private trip by URL; it never appears in
 *      user2's list.
 */
import { expect, test } from '@playwright/test';
import {
  createTrip,
  deleteAllE2eTrips,
  deleteTrip,
  loginAsUser,
  loginAsUser2,
  shot,
} from '../../helpers/live';
import { bucketButton, e2eTitle, isoDate, revealCreateForm, tripListCard } from '../../helpers/trip';

test('[TRIP-056] 빈 상태 — 여행이 없는 계정(user2)에서 안내 문구와 "새 여행 만들기" CTA가 폼에 포커스', async ({ page }) => {
  await loginAsUser2(page);
  await deleteAllE2eTrips(page);
  await page.goto('/trips');
  await expect(page.getByText(/예정 \d+ · 지난 여행 \d+ · 초안 \d+/)).toBeVisible(); // list loaded
  const anyCard = page.getByTestId('trip-list').getByRole('link');
  if ((await anyCard.count()) > 0) {
    test.skip(true, 'user2 owns non-[e2e] trips — empty state not reachable without deleting foreign data');
  }

  await expect(page.getByText('아직 여행이 없습니다.')).toBeVisible();
  await expect(page.getByText('제목만 있으면 시작할 수 있어요.')).toBeVisible();
  await page.getByRole('button', { name: '새 여행 만들기' }).click();
  await expect(page.locator('#trip-dashboard-create')).toBeVisible();
  await expect(page.getByTestId('trip-create-title')).toBeFocused();
  await shot(page, 'TRIP-056', 'empty-future');

  await bucketButton(page, '지난 여행').click();
  await expect(page.getByText('지난 여행이 없습니다.')).toBeVisible();
  await expect(page.getByText('종료된 여행이 생기면 여기에 모입니다.')).toBeVisible();
  await expect(page.getByRole('button', { name: '새 여행 만들기' })).toHaveCount(0);
  await shot(page, 'TRIP-056', 'empty-past');
});

test('[TRIP-057] 두 번째 사용자 격리 — user1의 비공개 여행은 user2 목록에 없고 URL 직접 접근도 거부', async ({ browser }) => {
  const ctx1 = await browser.newContext();
  const ctx2 = await browser.newContext();
  const page1 = await ctx1.newPage();
  const page2 = await ctx2.newPage();
  let tripId: string | null = null;
  try {
    await loginAsUser(page1);
    const title = e2eTitle('격리');
    tripId = (await createTrip(page1, { title, start: isoDate(12), end: isoDate(12), region: '경주' })).id;

    await loginAsUser2(page2);
    await page2.goto('/trips');
    await revealCreateForm(page2).catch(() => undefined); // mobile-safe; not required
    await expect(tripListCard(page2, title)).toHaveCount(0);
    await bucketButton(page2, '지난 여행').click();
    await expect(tripListCard(page2, title)).toHaveCount(0);

    await page2.goto(`/trips/${tripId}`);
    await expect(page2.getByTestId('trip-detail-error')).toBeVisible();
    await expect(page2.getByTestId('trip-layer-list')).toHaveCount(0);
    await expect(page2).not.toHaveURL(/\/login/); // user2 is logged in; it is a permission error, not auth
    await shot(page2, 'TRIP-057', 'forbidden');

    // the owner still sees it untouched
    await page1.goto(`/trips/${tripId}`);
    await expect(page1.getByRole('heading', { name: title }).first()).toBeVisible();
  } finally {
    if (tripId) await deleteTrip(page1, tripId).catch(() => undefined);
    await ctx1.close();
    await ctx2.close();
  }
});
