/**
 * TRIP-046 — a long edit session (> access-token lifetime, 10 min in prod:
 * apps/api/app/core/config.py `pinvi_access_token_minutes = 10`) keeps working without a
 * redirect to /login. Exceeds the 3-minute per-case budget on purpose — run it in its own
 * project/shard (see README "Open questions").
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  daySettingsButton,
  dayTab,
  e2eTitle,
  gotoTrip,
  isoDate,
  poiRows,
  preferFeature,
  selectDay,
  setPoiNote,
} from '../../helpers/trip';

const SESSION_MINUTES = Number(process.env.PINVI_E2E_SESSION_MINUTES ?? '11');

test('[TRIP-046] 10분 넘는 편집 세션 — 토큰 갱신 후에도 로그인 유지, 변경 저장 성공 @slow', async ({ page }) => {
  test.setTimeout((SESSION_MINUTES + 4) * 60_000);
  await loginAsUser(page);
  const { id } = await createTrip(page, { title: e2eTitle('세션'), start: isoDate(12), end: isoDate(13), region: '강릉' });
  try {
    await gotoTrip(page, id);
    await searchAndAddPlace(page, 1, '경포해변', preferFeature); // park/beach
    await selectDay(page, '1일차');
    await expect(poiRows(page)).toHaveCount(1);

    const started = Date.now();
    let tick = 0;
    while (Date.now() - started < SESSION_MINUTES * 60_000) {
      await page.waitForTimeout(60_000);
      tick += 1;
      // light, non-mutating interaction every minute (keeps the realtime socket + UI alive)
      await dayTab(page, tick % 2 === 0 ? '1일차' : '2일차').click();
      await expect(page).not.toHaveURL(/\/login/);
      await expect(page.getByTestId('trip-realtime-status')).toBeVisible();
    }

    // mutation after the access token must have expired at least once
    await selectDay(page, '1일차');
    await setPoiNote(page, 0, `[e2e] after ${SESSION_MINUTES}min`);
    await expect(poiRows(page).first()).toContainText(`after ${SESSION_MINUTES}min`);
    await daySettingsButton(page, 2).click();
    await page.locator('#trip-day-title-input').fill('세션 후');
    await page.getByRole('button', { name: '저장', exact: true }).click();
    await expect(dayTab(page, '세션 후')).toBeVisible();
    await expect(page).not.toHaveURL(/\/login/);
    await shot(page, 'TRIP-046', 'after-session');

    await gotoTrip(page, id);
    await expect(dayTab(page, '세션 후')).toBeVisible();
  } finally {
    await deleteTrip(page, id).catch(() => undefined);
  }
});
