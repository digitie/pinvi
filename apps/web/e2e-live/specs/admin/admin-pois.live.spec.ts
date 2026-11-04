// ADM-028..030 — user creates an [e2e] trip + POI (Map-source place); admin inspects POI/trip and round-trips link status.
// Two actors (user context + admin context). Cleanup: user deletes the trip; sweep deleteAllE2eTrips.
// Selectors re-verified on origin/main b1cef056: admin/pois/page.tsx (admin-pois-row-<attachment_id>), admin/pois/[poi_id]/page.tsx,
// admin/trips/page.tsx (admin-trips-row-<trip_id>)
// CAUTION: picking a Kakao/Naver result auto-fires a feature suggestion (services/feature_request.py) that cannot be [e2e]-prefixed.
import { expect, test } from '@playwright/test';
import { createTrip, deleteAllE2eTrips, deleteTrip, searchAndAddPlace, shot, isMobileProject } from '../../helpers/live';
import { E2E, maskedEmail, newAdminActor, newUserActor, requireEnv, runTag, waitForGet, type Actor } from '../../helpers/admin';

const PLACE = '안동하회마을'; // heritage
const notExternal = (rowText: string) => !/kakao|naver|카카오|네이버/i.test(rowText);

test.describe.serial('ADM POI admin (mutating, self-cleaning)', () => {
  let user: Actor;
  let admin: Actor;
  let tripId = '';
  let title = '';

  test.beforeAll(async ({ browser }) => {
    test.skip(isMobileProject(), 'desktop only');
    user = await newUserActor(browser);
    admin = await newAdminActor(browser);
    title = `${E2E} ADM-028 ${runTag()}`;
    const trip = await createTrip(user.page, { title, start: '2026-11-20', end: '2026-11-21', region: '안동' });
    tripId = trip.id;
    await user.page.goto(`/trips/${tripId}`);
    const added = await searchAndAddPlace(user.page, 1, PLACE, notExternal);
    expect(added).toContain('하회');
  });

  test.afterAll(async () => {
    try {
      // beforeAll skips on the mobile project before `user` exists
      if (user && tripId) await deleteTrip(user.page, tripId);
      if (user) await deleteAllE2eTrips(user.page);
    } finally {
      await user?.context.close();
      await admin?.context.close();
    }
  });

  test('ADM-028 admin POI list/detail shows masked owner and snapshot', async () => {
    const masked = maskedEmail(requireEnv('PINVI_E2E_USER_EMAIL'));
    const page = admin.page;
    await page.goto('/admin/pois');
    await page.getByTestId('admin-pois-search').fill(title);
    const listed = waitForGet(page, /\/admin\/pois\?.*q=/);
    await page.getByTestId('admin-pois-search-submit').click();
    await listed;
    const row = page.locator('[data-testid^="admin-pois-row-"]').filter({ hasText: title }).first(); // rowTestId on origin/main
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.getByRole('link').first().click();
    await expect(page).toHaveURL(/\/admin\/pois\/[0-9a-f-]{36}$/);
    const info = page.getByTestId('admin-poi-info');
    await expect(info).toBeVisible({ timeout: 30_000 });
    await expect(info).toContainText(title);
    await expect(info).toContainText(masked);
    await expect(page.getByTestId('admin-poi-snapshot')).toContainText(PLACE);
    await expect(page.getByTestId('admin-poi-operations')).toBeVisible();
    await expect(page.getByTestId('admin-poi-operation-dialog')).toHaveCount(0);
    await shot(page, 'ADM-028', 'poi-detail');
  });

  test('ADM-029 link status broken → normal round trip leaves [e2e] audit rows', async () => {
    const page = admin.page; // still on the POI detail page from ADM-028
    // Only ever mutate the [e2e] POI created in beforeAll.
    test.skip(!title, 'ADM-028 did not run');
    await expect(page.getByTestId('admin-poi-info')).toContainText(title);
    const select = page.getByTestId('admin-poi-link-status');
    test.skip((await select.count()) === 0, 'POI has no feature link (non-Map result picked?) — select hidden');
    const reason = `${E2E} ADM-029 link-status`;

    const save = async (value: 'broken' | 'normal') => {
      await select.selectOption(value);
      await page.getByTestId('admin-poi-link-status-save').click();
      await page.getByTestId('admin-poi-action-reason').fill(reason);
      const res = page.waitForResponse((r) => r.request().method() !== 'GET' && /\/admin\/pois\/[0-9a-f-]{36}/.test(r.url()));
      await page.getByTestId('admin-poi-action-confirm').click();
      expect((await res).status()).toBe(200);
    };

    const before = (await page.getByTestId('admin-poi-info').textContent()) ?? '';
    await save('broken');
    await expect(page.getByTestId('admin-poi-info')).not.toContainText('끊김 시각—');
    await expect(page.getByTestId('admin-poi-info')).toContainText(/끊김 시각\s*\d{4}\./);
    await shot(page, 'ADM-029', 'broken');
    await save('normal');
    await expect(page.getByTestId('admin-poi-info')).toContainText(/끊김 시각\s*—/);
    expect(before).toContain('끊김 시각');
    const audit = page.getByTestId('admin-poi-audit-list');
    await expect(audit.locator('tbody tr').filter({ hasText: reason })).toHaveCount(2, { timeout: 30_000 });
  });

  test('ADM-030 admin trips list finds the [e2e] trip with masked owner', async () => {
    const masked = maskedEmail(requireEnv('PINVI_E2E_USER_EMAIL'));
    const page = admin.page;
    await page.goto('/admin/trips');
    await page.getByTestId('admin-trips-search').fill(title);
    const listed = waitForGet(page, /\/admin\/trips\?.*q=/);
    await page.getByTestId('admin-trips-search-submit').click();
    await listed;
    const row = page.locator('[data-testid^="admin-trips-row-"]').filter({ hasText: title }).first(); // rowTestId on origin/main
    await expect(row).toBeVisible({ timeout: 30_000 });
    await expect(row).toContainText(masked);
    await row.getByRole('link').first().click();
    await expect(page).toHaveURL(new RegExp(`/admin/trips/${tripId}$`));
    await expect(page.locator('main h1')).toContainText(title);
    await shot(page, 'ADM-030', 'trip-detail');
  });
});
