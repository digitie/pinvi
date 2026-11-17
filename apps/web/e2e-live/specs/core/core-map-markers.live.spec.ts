/**
 * CORE — 지도 마커·라벨·모바일 지도 동작(소유자 요청 2026-11-16).
 *
 *  - CORE-040 원형 마커 + 상자 없는 이름 라벨 + 날씨 아이콘(components/map/CirclePlaceMarker.tsx)
 *  - CORE-041 마커 아이콘 고르기(components/trips/PoiEditor.tsx — 텍스트 입력 대신 아이콘 칩)
 *  - CORE-042 모바일 패널 = 아래 시트(지도가 시트보다 크게 보인다)
 *  - CORE-043 모바일 목록 탭 → 시트를 닫고 그 장소를 지도 가운데로(다시 눌러도)
 *  - CORE-044 내 위치 버튼 → 따라가기, 손으로 끌면 따라가기 해제, 다시 누르면 복귀
 *  - CORE-045 모바일 탐색 지도 feature 탭 → 상세 시트만(팝업과 이중 표시 없음)
 */
import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  clickableFeatureMarkers,
  closePanel,
  createTrip,
  deleteTrip,
  e2ePrefix,
  ensureFeatureMarkers,
  loginAsUser,
  openPanel,
  poiRows,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
} from '../../helpers/live';
import { isMobileViewport, PLACES, tripPins, waitForMapCanvas, type Box } from '../../helpers/core';

/**
 * '내 위치' 버튼을 눌러 따라가기를 켠다. 계정에 위치 동의가 없으면 동의 다이얼로그에서 동의한다(테스트 계정에
 * LBS 동의 기록이 남는다).
 *
 * 다이얼로그는 버튼을 누른 뒤 서버 동의 조회(`getLocationConsentState({ force: true })`)가 끝나야 열린다.
 * 예전 `consent.isVisible({ timeout })`은 기다리지 않아(Playwright는 그 timeout을 무시한다) 아직 열리지 않은
 * 다이얼로그를 "없음"으로 읽었고, 동의하지 않은 채 follow를 기다리다 실패했다(2026-11-17 prod: 동의 기록 0건).
 * 그래서 "다이얼로그가 떴다 / 측위를 시작했다 / 위치 오류 안내가 떴다" 중 하나가 될 때까지 기다린다.
 */
async function startFollowing(page: Page, button: Locator): Promise<void> {
  await button.click();
  const consent = page.getByTestId('location-consent-agree');
  const started = page.locator('[data-testid="map-my-location"]:not([data-follow-mode="off"])');
  const failed = page.getByTestId('my-location-error');
  await expect(consent.or(started).or(failed).first()).toBeVisible({ timeout: 20_000 });
  await expect(failed, '위치 오류 안내 없이 측위를 시작한다').toHaveCount(0);
  if (await consent.isVisible()) {
    await consent.click();
    // 저장(PUT /users/me/consents)에 실패하면 다이얼로그가 오류 문구와 함께 열린 채 남는다.
    await expect(consent, '위치 동의를 저장하면 다이얼로그가 닫힌다').toBeHidden({ timeout: 20_000 });
  }
  await expect(button).toHaveAttribute('data-follow-mode', 'follow', { timeout: 20_000 });
  await expect(button).toHaveAttribute('data-follow-ready', 'true', { timeout: 20_000 });
}

const centreOffset = async (page: Page, poiTitle: string) => {
  const map = (await page.getByTestId('trip-detail-map').boundingBox()) as Box;
  const dot = page
    .locator('.maplibregl-marker.trip-map-marker')
    .filter({ hasText: poiTitle })
    .first()
    .getByTestId('circle-place-marker-dot');
  const box = (await dot.boundingBox()) as Box;
  return {
    dx: Math.abs(box.x + box.width / 2 - (map.x + map.width / 2)),
    dy: Math.abs(box.y + box.height / 2 - (map.y + map.height / 2)),
    mapHeight: map.height,
  };
};

test.describe('CORE map markers', () => {
  let tripId: string | null = null;
  let names: string[] = [];

  test.beforeEach(async ({ page }, testInfo) => {
    await loginAsUser(page);
    if (testInfo.title.startsWith('CORE-045') || testInfo.title.startsWith('CORE-046')) return;
    const { id } = await createTrip(page, {
      title: `${e2ePrefix} CORE-markers ${Date.now()}`,
      start: '2026-11-05',
      end: '2026-11-05',
    });
    tripId = id;
    await page.goto(`/trips/${id}`);
    names = [
      await searchAndAddPlace(page, 1, PLACES.north),
      await searchAndAddPlace(page, 1, PLACES.south),
    ];
    await closePanel(page);
  });

  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId);
    tripId = null;
  });

  test('CORE-040 장소 마커는 원 + 상자 없는 이름 라벨(+ 날씨 아이콘)', async ({ page }) => {
    await waitForMapCanvas(page);
    const pins = tripPins(page);
    await expect(pins).toHaveCount(2, { timeout: 30_000 });
    await waitForMapIdle(page);
    for (const name of names) {
      const pin = pins.filter({ hasText: name }).first();
      const dot = pin.getByTestId('circle-place-marker-dot');
      const box = (await dot.boundingBox()) as Box;
      expect(Math.round(box.width), `${name} 원 지름`).toBeLessThanOrEqual(24);
      expect(Math.abs(box.width - box.height)).toBeLessThan(1);
      const label = pin.getByTestId('circle-place-marker-label');
      await expect(label).toContainText(name.slice(0, 4));
      const style = await label.evaluate((el) => {
        const s = getComputedStyle(el);
        return { bg: s.backgroundColor, shadow: s.boxShadow };
      });
      expect(style, `${name} 라벨은 상자 없는 글자`).toEqual({ bg: 'rgba(0, 0, 0, 0)', shadow: 'none' });
      expect(((await label.boundingBox()) as Box).x).toBeGreaterThanOrEqual(box.x + box.width - 1);
      // 날씨 카드가 있는 장소는 라벨 옆에 아이콘이 붙는다(카드가 없으면 그리지 않는다).
      const legend = page.locator('[data-testid="trip-map-marker-style"]').filter({ hasText: name }).first();
      const weather = await legend.getAttribute('data-marker-weather');
      await expect(pin.getByTestId('place-weather-glyph')).toHaveCount(weather ? 1 : 0);
    }
    await shot(page, 'CORE-040', 'markers');
  });

  test('CORE-041 마커 아이콘을 아이콘 칩으로 골라 저장한다', async ({ page }) => {
    await openPanel(page);
    const row = poiRows(page).filter({ hasText: names[0]! }).first();
    await row.getByRole('button', { name: '마커 편집' }).click();
    const editor = page.getByTestId('poi-editor');
    await editor.getByRole('button', { name: '아이콘', exact: true }).click();
    await expect(editor.getByLabel('maki 아이콘')).toHaveCount(0);
    const icons = editor.getByRole('group', { name: '마커 아이콘' });
    await icons.getByRole('button', { name: '카페' }).click();
    await expect(icons.getByRole('button', { name: '카페' })).toHaveAttribute('aria-pressed', 'true');
    const patched = page.waitForResponse(
      (r) => r.request().method() === 'PATCH' && /\/pois\/[0-9a-f-]{36}$/.test(new URL(r.url()).pathname),
    );
    await editor.getByRole('button', { name: '저장' }).click();
    expect((await patched).status()).toBeLessThan(400);
    const legend = page.locator('[data-testid="trip-map-marker-style"]').filter({ hasText: names[0]! }).first();
    await expect(legend).toHaveAttribute('data-marker-icon', 'cafe', { timeout: 15_000 });
    await shot(page, 'CORE-041', 'icon-picked');
  });

  test('CORE-042 (모바일) 패널은 아래 시트 — 위로 보이는 지도가 시트보다 크다', async ({ page }) => {
    test.skip(!isMobileViewport(page), 'mobile project only (390x844)');
    await waitForMapCanvas(page);
    await openPanel(page);
    const panel = (await page.getByTestId('trip-detail-panel').boundingBox()) as Box;
    const map = (await page.getByTestId('trip-detail-map').boundingBox()) as Box;
    const top = (await page.getByTestId('trip-top-panel').boundingBox()) as Box;
    expect(Math.abs(panel.width - map.width)).toBeLessThan(2);
    expect(Math.abs(panel.y + panel.height - (map.y + map.height))).toBeLessThan(2);
    expect(panel.y - (top.y + top.height), '보이는 지도 > 시트').toBeGreaterThan(panel.height);
    await shot(page, 'CORE-042', 'sheet');
    await page.getByRole('button', { name: '패널 펼치기' }).click();
    const expanded = (await page.getByTestId('trip-detail-panel').boundingBox()) as Box;
    expect(expanded.height).toBeGreaterThan(panel.height);
    await page.getByRole('button', { name: '패널 줄이기' }).click();
  });

  test('CORE-043 (모바일) 목록에서 장소를 누르면 지도 가운데로 — 지도를 옮긴 뒤 다시 눌러도', async ({ page }) => {
    test.skip(!isMobileViewport(page), 'mobile project only (390x844)');
    await waitForMapCanvas(page);
    await expect(tripPins(page)).toHaveCount(2, { timeout: 30_000 });
    const name = names[1]!;
    const tapRow = async () => {
      await openPanel(page);
      await poiRows(page).filter({ hasText: name }).first().locator('button[aria-current]').first().tap();
      await expect(page.getByTestId('trip-detail-panel')).toBeHidden();
    };
    await tapRow();
    await expect.poll(async () => (await centreOffset(page, name)).dx, { timeout: 15_000 }).toBeLessThan(6);
    const first = await centreOffset(page, name);
    expect(first.dy).toBeLessThan(first.mapHeight / 4);
    await shot(page, 'CORE-043', 'centred');
    // 지도를 손으로 옮긴 뒤 같은 장소를 다시 누른다.
    const box = (await page.getByTestId('trip-detail-map').boundingBox()) as Box;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.6);
    await page.mouse.down();
    await page.mouse.move(box.x + 40, box.y + box.height * 0.4, { steps: 10 });
    await page.mouse.up();
    await expect.poll(async () => (await centreOffset(page, name)).dx).toBeGreaterThan(40);
    await tapRow();
    await expect.poll(async () => (await centreOffset(page, name)).dx, { timeout: 15_000 }).toBeLessThan(6);
  });

  test('CORE-044 내 위치 버튼 — 따라가기, 끌면 해제, 다시 누르면 복귀', async ({ page, context }) => {
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude: 37.5665, longitude: 126.978 });
    await waitForMapCanvas(page);
    const button = page.getByTestId('map-my-location');
    await expect(button).toHaveAttribute('data-follow-mode', 'off');
    const size = (await button.boundingBox()) as Box;
    expect(size.width).toBeGreaterThanOrEqual(40);
    await startFollowing(page, button);
    await waitForMapIdle(page);
    const map = (await page.getByTestId('trip-detail-map').boundingBox()) as Box;
    await page.mouse.move(map.x + map.width / 2, map.y + map.height * 0.6);
    await page.mouse.down();
    await page.mouse.move(map.x + map.width / 2 - 80, map.y + map.height * 0.5, { steps: 8 });
    await page.mouse.up();
    await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
    await expect(button).toHaveAccessibleName('내 위치로 돌아가기');
    await button.click();
    await expect(button).toHaveAttribute('data-follow-mode', 'follow');
    await shot(page, 'CORE-044', 'follow');
  });

  test('CORE-045 (모바일) 탐색 지도 장소를 누르면 상세 시트만 — 팝업과 이중 표시 없음', async ({ page }) => {
    test.skip(!isMobileViewport(page), 'mobile project only (390x844)');
    await page.goto('/map');
    await waitForMapCanvas(page);
    await ensureFeatureMarkers(page, 1);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin, 'a tappable feature pin').toBeTruthy();
    await pin!.tap();
    await expect(page.getByTestId('feature-detail-modal')).toBeVisible({ timeout: 15_000 });
    // 같은 장소가 지도 팝업(상세보기 버튼)으로 한 번 더 그려지지 않는다.
    await expect(page.locator('.maplibregl-popup')).toHaveCount(0);
    await shot(page, 'CORE-045', 'sheet-only');
  });

  test('CORE-046 탐색 지도 내 위치 버튼 — 따라가기, 끌면 해제, 다시 누르면 복귀', async ({ page, context }) => {
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude: 37.5665, longitude: 126.978 });
    await page.goto('/map');
    await waitForMapCanvas(page);
    const button = page.getByTestId('map-my-location');
    await expect(button).toHaveAttribute('data-follow-mode', 'off');
    await startFollowing(page, button);
    await waitForMapIdle(page);
    const canvas = (await page.locator('.maplibregl-canvas').first().boundingBox()) as Box;
    await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height * 0.6);
    await page.mouse.down();
    await page.mouse.move(canvas.x + canvas.width / 2 - 80, canvas.y + canvas.height * 0.5, { steps: 8 });
    await page.mouse.up();
    await expect(button).toHaveAttribute('data-follow-mode', 'tracking');
    await button.click();
    await expect(button).toHaveAttribute('data-follow-mode', 'follow');
    await shot(page, 'CORE-046', 'follow');
  });

  test('CORE-047 (모바일) 장소 정보 패널이 열리면 내 위치 버튼이 패널 위로 올라간다', async ({ page }) => {
    test.skip(!isMobileViewport(page), 'mobile project only (390x844)');
    await waitForMapCanvas(page);
    const button = page.getByTestId('map-my-location');
    const before = (await button.boundingBox()) as Box;
    await openPanel(page);
    await poiRows(page).filter({ hasText: names[0]! }).first().locator('button[aria-current]').first().tap();
    const panel = page.getByTestId('place-info-panel');
    await expect(panel).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('map-my-location-control')).toHaveAttribute('data-lifted', 'true');
    const panelBox = (await panel.boundingBox()) as Box;
    const lifted = (await button.boundingBox()) as Box;
    expect(lifted.y + lifted.height, '버튼이 패널 위').toBeLessThanOrEqual(panelBox.y);
    expect(lifted.y).toBeLessThan(before.y);
    await button.click({ trial: true });
    await shot(page, 'CORE-047', 'lifted');
  });
});
