/**
 * POI area — 마커/행 선택 시 장소 정보 패널(요약 + 접힌 항목), 영업 정보 저장·다시 읽어오기, 지도 앱 링크.
 * Cases: POI-045, POI-046, POI-047, POI-048(mobile).
 * Selectors: components/trips/PlaceInfoPanel.tsx (place-info-*), WeatherBadge.tsx (weather-badge).
 * API: GET /trips/{id}/pois/{poi}/place-details, POST …/place-details/refresh (배포 뒤에만 존재).
 */
import { expect, test, type Page, type Response } from '@playwright/test';
import { closePanel, createTrip, deleteTrip, loginAsUser, searchAndAddPlace } from '../../helpers/live';
import { e2eName, gotoTrip, poiRow, selectDay, snap } from '../../helpers/poi';

const START = '2026-11-20';
const END = '2026-11-21';
const PLACE = '안동하회마을';

let tripId: string | null = null;

test.afterEach(async ({ page }) => {
  if (!tripId) return;
  const id = tripId;
  tripId = null;
  await deleteTrip(page, id);
});

function isPlaceDetailsGet(response: Response): boolean {
  return response.request().method() === 'GET' && /\/pois\/[0-9a-f-]{36}\/place-details$/.test(new URL(response.url()).pathname);
}

async function tripWithPlace(page: Page, label: string): Promise<{ id: string; poiId: string; title: string }> {
  await loginAsUser(page);
  const trip = await createTrip(page, { title: e2eName(label), start: START, end: END });
  tripId = trip.id;
  await gotoTrip(page, trip.id);
  await selectDay(page, 1);
  const created = page.waitForResponse(
    (r) => r.request().method() === 'POST' && /\/trips\/[0-9a-f-]{36}\/pois$/.test(new URL(r.url()).pathname),
  );
  const title = await searchAndAddPlace(page, 1, PLACE, (t) => t.includes('하회'));
  const body = (await (await created).json()) as { data: { attachment_id: string } };
  return { id: trip.id, poiId: body.data.attachment_id, title };
}

function panel(page: Page) {
  return page.getByTestId('place-info-panel');
}

async function openPanelFromRow(page: Page, title: string): Promise<Response> {
  const details = page.waitForResponse(isPlaceDetailsGet);
  await poiRow(page, title).getByRole('button').first().click();
  await expect(panel(page)).toBeVisible();
  return details;
}

test.describe('POI place info (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, 'desktop-only cases');
  test.setTimeout(180_000);

  test('POI-045 장소 정보 패널 — 요약 + 접힌 항목(날씨·영업 정보·메모·링크·지도 앱), 지도 앱 링크', async ({ page }) => {
    const { title } = await tripWithPlace(page, '장소 정보');
    // 새 장소는 추가 직후 선택된다 — 패널을 닫았다가 행으로 다시 연다.
    if (await panel(page).isVisible()) await panel(page).getByTestId('place-info-close').click();
    await expect(panel(page)).toBeHidden();
    const response = await openPanelFromRow(page, title);
    expect(response.status()).toBe(200);
    const p = panel(page);
    await expect(p.getByTestId('place-info-title')).toHaveText(title);
    await expect.soft(p.getByTestId('weather-badge'), '요약 날씨 배지').toBeVisible({ timeout: 45_000 });
    for (const key of ['weather', 'hours', 'memo', 'links', 'maps']) {
      await expect(p.getByTestId(`place-info-${key}-toggle`)).toHaveAttribute('aria-expanded', 'false');
      await expect(p.getByTestId(`place-info-${key}`)).toHaveCount(0);
    }
    await p.getByTestId('place-info-hours-toggle').click();
    const hours = p.getByTestId('place-info-hours');
    await expect(hours.getByTestId('place-info-hours-body').or(hours.getByTestId('place-info-hours-empty'))).toBeVisible();
    if (await hours.getByTestId('place-info-hours-body').isVisible()) {
      await expect(hours.getByTestId('place-info-hours-source')).toContainText('출처: 공공데이터');
    }
    await p.getByTestId('place-info-maps-toggle').click();
    await expect(p.getByTestId('place-info-hours')).toHaveCount(0);
    await expect(p.getByTestId('place-info-map-naver')).toHaveAttribute('href', /^https:\/\/map\.naver\.com\/p\/search\/.+\?c=12\d\.\d+,3\d\.\d+,15/);
    await expect(p.getByTestId('place-info-map-kakao')).toHaveAttribute('href', /^https:\/\/map\.kakao\.com\/link\/map\/.+,3\d\.\d+,12\d\.\d+$/);
    await expect(p.getByTestId('place-info-map-google')).toHaveAttribute('href', /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=3\d\.\d+,12\d\.\d+$/);
    await expect(page.locator('.maplibregl-popup').filter({ hasText: title })).toHaveCount(0);
    await snap(page, 'POI-045', 'panel');
    await p.getByTestId('place-info-close').click();
    await expect(panel(page)).toBeHidden();
  });

  test('POI-046 다시 읽어오기 — 덮어쓰기 성공 후 60초 안 재요청은 안내(429)', async ({ page }) => {
    const { title } = await tripWithPlace(page, '다시 읽기');
    if (!(await panel(page).isVisible())) await openPanelFromRow(page, title);
    const p = panel(page);
    await p.getByTestId('place-info-hours-toggle').click();
    const button = p.getByTestId('place-info-refetch');
    await expect(button).toBeEnabled({ timeout: 30_000 });
    const first = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith('/place-details/refresh'));
    await button.click();
    const firstResponse = await first;
    // 처음 열 때 이미 저장했으므로 60초 안이면 429일 수 있다 — 둘 다 사용자에게 상태를 알린다.
    if (firstResponse.status() === 200) {
      await expect(p.getByTestId('place-info-refetch-done')).toBeVisible();
    } else {
      expect(firstResponse.status()).toBe(429);
      await expect(p.getByTestId('place-info-refetch-error')).toContainText('다시 읽어올 수 있습니다');
    }
    const second = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith('/place-details/refresh'));
    await button.click();
    expect((await second).status()).toBe(429);
    await expect(p.getByTestId('place-info-refetch-error')).toContainText(/\d+초 뒤에 다시 읽어올 수 있습니다/);
    await snap(page, 'POI-046', 'refetch-rate-limit');
  });

  test('POI-047 장소 삭제 후 다시 추가하면 영업 정보를 새로 받는다', async ({ page }) => {
    const { id, title } = await tripWithPlace(page, '재추가');
    if (await panel(page).isVisible()) await panel(page).getByTestId('place-info-close').click();
    const firstBody = (await (await openPanelFromRow(page, title)).json()) as { data: { poi_id: string; fetched_at: string | null; status: string } };
    await panel(page).getByTestId('place-info-close').click();
    await poiRow(page, title).getByRole('button', { name: '장소 삭제' }).click();
    await expect(poiRow(page, title)).toHaveCount(0);
    await gotoTrip(page, id);
    await selectDay(page, 1);
    const readdTitle = await searchAndAddPlace(page, 1, PLACE, (t) => t.includes('하회'));
    if (await panel(page).isVisible()) await panel(page).getByTestId('place-info-close').click();
    const secondBody = (await (await openPanelFromRow(page, readdTitle)).json()) as { data: { poi_id: string; fetched_at: string | null; status: string } };
    expect(secondBody.data.poi_id).not.toBe(firstBody.data.poi_id);
    if (firstBody.data.fetched_at && secondBody.data.fetched_at) {
      expect(Date.parse(secondBody.data.fetched_at)).toBeGreaterThan(Date.parse(firstBody.data.fetched_at));
    } else {
      test.info().annotations.push({ type: 'poi', description: `출처 장애로 저장 안 됨: ${firstBody.data.status}/${secondBody.data.status}` });
    }
  });
});

test.describe('POI place info (mobile)', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile-only case');
  test.setTimeout(180_000);

  test('POI-048 모바일 — 마커 탭 → 지도 아래쪽 장소 정보 패널, 지도 앱 링크', async ({ page }) => {
    const { poiId } = await tripWithPlace(page, '모바일 패널');
    await closePanel(page).catch(() => {});
    if (await panel(page).isVisible()) await panel(page).getByTestId('place-info-close').click();
    const marker = page.locator(`[data-interaction-id="poi:${poiId}"]`).first();
    await expect(marker).toBeVisible({ timeout: 30_000 });
    await marker.tap();
    const p = panel(page);
    await expect(p).toBeVisible();
    const box = await p.boundingBox();
    const viewport = page.viewportSize();
    expect(box && viewport ? box.y + box.height : 0, '패널은 화면 아래쪽에 붙는다').toBeGreaterThan((viewport?.height ?? 0) / 2);
    await p.getByTestId('place-info-maps-toggle').tap();
    await expect(p.getByTestId('place-info-map-naver')).toHaveAttribute('href', /map\.naver\.com/);
    await expect(p.getByTestId('place-info-map-kakao')).toHaveAttribute('href', /map\.kakao\.com/);
    await expect(p.getByTestId('place-info-map-google')).toHaveAttribute('href', /google\.com\/maps/);
    await snap(page, 'POI-048', 'mobile-panel');
    await p.getByTestId('place-info-close').tap();
    await expect(p).toBeHidden();
  });
});
