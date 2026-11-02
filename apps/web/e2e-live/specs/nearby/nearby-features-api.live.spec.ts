/**
 * NEAR — nearby categories exposed as ordinary Map features (parking lots from
 * 전국주차장표준데이터, category 06010000 "주차장") and the transport API error contract as seen
 * through the browser session (404 / 400, never 5xx on list/status).
 *
 * References: kor-travel-map src/kortravelmap/providers/standard_data.py (PARKING_CATEGORY),
 * src/kortravelmap/category/_definitions.py ("06": {"01": "주차장", …}), PinVi
 * apps/api/app/api/v1/transport.py (error codes), apps/web/components/map/MapSearchBox.tsx
 * (`map-search-result-feature`, category_label), FeatureDetailCardBody.tsx (`…-category`).
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot, waitForRequest } from '../../helpers/live';
import { STATUS_RE, apiOriginFrom, waitForControls } from '../../helpers/nearby';

test.setTimeout(180_000);

test.describe('NEAR nearby feature families', () => {
  test.skip(({ isMobile }) => !!isMobile, 'desktop flow (search → popup → 상세보기)');

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-030 parking lots are searchable Map features named "… 주차장" with category 주차장', async ({ page }) => {
    await page.goto('/map');
    await waitForControls(page);
    const search = page.getByTestId('map-search').first();
    await search.getByRole('textbox', { name: '장소·주소 검색' }).fill('주차장');
    const featureRows = search.getByTestId('map-search-result-feature');
    await expect(featureRows.first()).toBeVisible({ timeout: 20_000 });
    const texts = await featureRows.allTextContents();
    const parkingRow = texts.findIndex((t) => t.includes('주차장'));
    expect(parkingRow, `a Map feature row mentions 주차장: ${JSON.stringify(texts)}`).toBeGreaterThanOrEqual(0);
    await featureRows.nth(parkingRow).click();
    const open = page.getByTestId('feature-map-detail-open');
    await expect(open).toBeVisible({ timeout: 20_000 });
    await open.click();
    const body = page.getByTestId('feature-detail-card-body');
    await expect(body).toBeVisible({ timeout: 20_000 });
    await expect(body).toHaveAttribute('data-kind', 'place');
    await expect(body.getByTestId('feature-detail-card-body-category')).toContainText(/주차/);
    await shot(page, 'NEAR-030', 'parking-feature-detail');
  });
});

test.describe('NEAR transport API contract through the browser session', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('NEAR-035 unknown transport feature id → 404 TRANSPORT_FEATURE_NOT_FOUND (no 5xx)', async ({ page }) => {
    const status = waitForRequest(page, STATUS_RE);
    await page.goto('/map');
    const origin = apiOriginFrom(await status);
    for (const path of ['fuel-stations', 'rest-areas', 'highway-incidents', 'airports']) {
      const res = await page.request.get(`${origin}/transport/${path}/e2e-does-not-exist`);
      expect(res.status(), `${path} 404`).toBe(404);
      expect(await res.text()).toContain('TRANSPORT_FEATURE_NOT_FOUND');
    }
    const bad = await page.request.get(`${origin}/transport/fuel-stations/${encodeURIComponent('bad id!')}`);
    expect([400, 404, 422]).toContain(bad.status()); // path pattern ^[A-Za-z0-9_-]{1,128}$
  });

  test('NEAR-036 bad layers / bbox / zoom are 4xx validation errors; status and valid list are 200', async ({ page }) => {
    const status = waitForRequest(page, STATUS_RE);
    await page.goto('/map');
    const statusRes = await status;
    expect(statusRes.status()).toBe(200);
    const origin = apiOriginFrom(statusRes);
    const base = `${origin}/transport/markers-in-bounds`;
    const badLayer = await page.request.get(`${base}?bbox=126.9,37.4,127.1,37.6&zoom=12&layers=bogus`);
    expect(badLayer.status()).toBe(400);
    expect(await badLayer.text()).toContain('VALIDATION_ERROR');
    const badBbox = await page.request.get(`${base}?bbox=not-a-bbox&zoom=12&layers=airport`);
    expect(badBbox.status()).toBe(400);
    const badZoom = await page.request.get(`${base}?bbox=126.9,37.4,127.1,37.6&zoom=99&layers=airport`);
    expect([400, 422]).toContain(badZoom.status());
    // Out-of-Korea bbox is clamped/clipped, never an error: empty ok result.
    const abroad = await page.request.get(`${base}?bbox=139.5,35.5,139.9,35.8&zoom=12&layers=airport`);
    expect(abroad.status()).toBe(200);
    const body = (await abroad.json()) as { data: { layers: Array<{ layer: string; status: string; items: unknown[] }> } };
    expect(body.data.layers).toHaveLength(1);
    expect(body.data.layers[0]!.status).not.toBe('disabled');
    expect(body.data.layers[0]!.items).toHaveLength(0);
  });
});
