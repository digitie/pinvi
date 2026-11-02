/**
 * NEAR-027 — the public shared trip page must not render the transport panel nor call
 * `/transport/*` (login required; a 401 there would bounce the viewer to /login).
 *
 * UI reference (PinVi main b1cef056): apps/web/components/trips/SharedTripView.tsx does not pass
 * `transportLayers` to TripMapView, whose default is false (docs/execplan/map-transport-integration.md §7 P0).
 *
 * Needs helper `createShareLink(page, tripId)` (see README "helpers needed"); kept in its own file so
 * the other NEAR specs compile without it.
 */
import { expect, test } from '@playwright/test';
import {
  createShareLink,
  createTrip,
  deleteAllE2eTrips,
  deleteTrip,
  e2ePrefix,
  loginAsUser,
  searchAndAddPlace,
  shot,
} from '../../helpers/live';
import { TransportRecorder, controls } from '../../helpers/nearby';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.setTimeout(180_000);

test('NEAR-027 shared trip view has no transport controls and makes no /transport requests', async ({ page, browser }) => {
  await loginAsUser(page);
  const trip = await createTrip(page, {
    title: `${e2ePrefix} NEAR shared ${Date.now()}`,
    start: '2026-11-05',
    end: '2026-11-06',
  });
  try {
    await page.goto(`/trips/${trip.id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (row) => row.includes('장소'));
    const { url: shareUrl } = await createShareLink(page);

    // Anonymous context — a viewer who received the link.
    const anon = await browser.newPage();
    const rec = new TransportRecorder(anon);
    await anon.goto(shareUrl);
    await expect(anon.locator('.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
    await expect(anon.locator('.maplibregl-marker.trip-map-marker')).toHaveCount(1, { timeout: 30_000 });
    await expect(controls(anon)).toHaveCount(0);
    expect(anon.url()).not.toMatch(/\/login/);
    await anon.waitForTimeout(1_500);
    expect(rec.urls, 'no /transport/* traffic from the shared page').toHaveLength(0);
    await shot(anon, 'NEAR-027', 'shared-no-transport');
    await anon.close();
  } finally {
    await deleteTrip(page, trip.id).catch(() => undefined);
    await deleteAllE2eTrips(page);
  }
});
