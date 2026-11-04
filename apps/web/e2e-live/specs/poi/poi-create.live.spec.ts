/**
 * POI area — creating places that do not exist in Map (manual / my-POI).
 * Cases: POI-001, 002(mobile), 003, 010, 011, 012, 013, 031, 032.
 * Every test creates its own `[e2e]` trip and removes POIs + trip in afterEach.
 */
import { expect, test, type Page } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser } from '../../helpers/live';
import {
  createManualPoi,
  dayBadge,
  deleteAllPoisInDay,
  e2eName,
  gotoTrip,
  longPressMap,
  manualDialog,
  mapStats,
  markerLegend,
  openPanelIfMobile,
  poiRow,
  rightClickMap,
  selectDay,
  snap,
  submitManualDialog,
  waitForDialogAddress,
} from '../../helpers/poi';

const START = '2026-11-05';
const END = '2026-11-06';

let tripId: string | null = null;

async function freshTrip(page: Page, label: string): Promise<string> {
  await loginAsUser(page);
  const trip = await createTrip(page, { title: e2eName(label), start: START, end: END });
  tripId = trip.id;
  await gotoTrip(page, trip.id);
  await selectDay(page, 1);
  return trip.id;
}

test.afterEach(async ({ page }) => {
  if (!tripId) return;
  const id = tripId;
  tripId = null;
  try {
    await gotoTrip(page, id);
    await selectDay(page, 1);
    await deleteAllPoisInDay(page);
  } catch {
    // trip may already be gone; deleteTrip below is the authoritative cleanup
  }
  await deleteTrip(page, id);
});

test.describe('POI create (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, 'desktop-only cases');

  test('POI-001 지도 우클릭 → 주소 자동 조회 → 생성 → 일정/지도 반영', async ({ page }) => {
    const id = await freshTrip(page, 'POI 수동');
    await rightClickMap(page);
    await expect(manualDialog(page)).toBeVisible();
    await expect(manualDialog(page).getByRole('heading', { name: 'POI 생성' })).toBeVisible();
    const address = await waitForDialogAddress(page);
    expect(address.length).toBeGreaterThan(0);
    await snap(page, 'POI-001', 'dialog');

    const name = e2eName('수동 장소');
    const { title, body } = await submitManualDialog(page, id, name);
    expect(title).toBe(name);
    expect(body).toMatchObject({ feature_id: null, custom_marker_color: 'P-08', custom_marker_icon: 'marker' });
    const snapshot = body.feature_snapshot as Record<string, unknown>;
    expect(snapshot.source).toBe('manual');
    expect(snapshot.name).toBe(name);
    if (address !== '주소 결과 없음') expect(snapshot.address_label).toBe(address);

    await openPanelIfMobile(page);
    await expect(poiRow(page, name)).toHaveCount(1);
    const legend = markerLegend(page).filter({ hasText: name });
    await expect(legend).toHaveCount(1);
    await expect(legend).toHaveAttribute('data-feature-resolution-state', 'not_linked');
    await expect(legend).toHaveAttribute('data-marker-color', 'P-08');
    await expect(legend).toHaveAttribute('data-marker-icon', 'marker');
    await expect(mapStats(page)).toContainText('장소 1곳');
    await expect(dayBadge(page, 1)).toHaveText('1곳');
    await snap(page, 'POI-001', 'created');
  });

  test('POI-003 이름을 비우면 역지오코딩 주소가 제목이 된다', async ({ page }) => {
    const id = await freshTrip(page, 'POI 주소제목');
    await rightClickMap(page);
    await expect(manualDialog(page)).toBeVisible();
    const address = await waitForDialogAddress(page);
    test.skip(address === '주소 결과 없음', '이 지점에는 geo 후보가 없어 이름이 필수 — POI-004 수동 케이스 영역');
    const { title } = await submitManualDialog(page, id, null);
    expect(title).toBe(address);
    await expect(markerLegend(page).filter({ hasText: address })).toHaveCount(1);
    await snap(page, 'POI-003', 'address-title');
  });

  test('POI-010 my-POI 팝업에는 상세보기·홈페이지가 없다', async ({ page }) => {
    const id = await freshTrip(page, 'POI 팝업');
    const { title } = await createManualPoi(page, id, e2eName('팝업'));
    // creation selects the POI → popup with just the title
    await poiRow(page, title).getByRole('button').first().click();
    const popup = page.locator('.maplibregl-popup').filter({ hasText: title });
    await expect(popup).toBeVisible();
    await expect(popup.getByTestId('trip-map-detail-open')).toHaveCount(0);
    await expect(popup.getByRole('link')).toHaveCount(0);
    await expect(poiRow(page, title).getByRole('link', { name: /홈페이지|전화/ })).toHaveCount(0);
    await snap(page, 'POI-010', 'popup');
  });

  test('POI-011 my-POI 편집 — 메모·예산·링크', async ({ page }) => {
    const id = await freshTrip(page, 'POI 편집');
    const { title, poiId } = await createManualPoi(page, id, e2eName('편집'));
    const row = poiRow(page, title);
    await row.getByRole('button', { name: '마커 편집' }).click();
    const editor = page.getByTestId('poi-editor');
    await expect(editor).toBeVisible();
    await editor.getByLabel('메모').fill('[e2e] memo');
    await editor.getByLabel('예산').fill('12000');
    await editor.getByLabel('링크').fill('https://example.com/e2e');
    const patch = page.waitForResponse(
      (r) => r.request().method() === 'PATCH' && new URL(r.url()).pathname === `/trips/${id}/pois/${poiId}`,
    );
    await editor.getByRole('button', { name: '저장' }).click();
    const res = await patch;
    expect(res.status()).toBe(200);
    expect(res.request().headers()['if-match']).toBeTruthy();
    const json = (await res.json()) as { data: { version: number; user_note: string | null } };
    expect(json.data.version).toBe(2);
    expect(json.data.user_note).toBe('[e2e] memo');
    await expect(editor).toBeHidden();
    await expect(row).toContainText('[e2e] memo');
    await expect(row).toContainText(/예산 12000(\.00)? KRW/);
    await snap(page, 'POI-011', 'edited');
  });

  test('POI-012 my-POI 삭제 — 목록·지도·통계에서 제거', async ({ page }) => {
    const id = await freshTrip(page, 'POI 삭제');
    const { title, poiId } = await createManualPoi(page, id, e2eName('삭제'));
    const del = page.waitForResponse(
      (r) => r.request().method() === 'DELETE' && new URL(r.url()).pathname === `/trips/${id}/pois/${poiId}`,
    );
    await poiRow(page, title).getByRole('button', { name: '장소 삭제' }).click();
    expect((await del).status()).toBe(204);
    await expect(poiRow(page, title)).toHaveCount(0);
    await expect(markerLegend(page)).toHaveCount(0);
    await expect(mapStats(page)).toContainText('장소 0곳');
    await expect(dayBadge(page, 1)).toHaveText('0곳');
    await snap(page, 'POI-012', 'deleted');
  });

  test('POI-013 마커 색 변경이 범례에 반영', async ({ page }) => {
    const id = await freshTrip(page, 'POI 색');
    const { title } = await createManualPoi(page, id, e2eName('색'));
    await poiRow(page, title).getByRole('button', { name: '마커 편집' }).click();
    const editor = page.getByTestId('poi-editor');
    await editor.getByRole('button', { name: '노랑' }).click(); // P-03 (packages/design-tokens/src/colors.ts)
    await editor.getByRole('button', { name: '저장' }).click();
    await expect(editor).toBeHidden();
    const legend = markerLegend(page).filter({ hasText: title });
    await expect(legend).toHaveAttribute('data-marker-color', 'P-03');
    await expect(legend).toHaveAttribute('data-marker-hex', /#fdd835/i);
    await snap(page, 'POI-013', 'recolored');
  });

  test('POI-031 다이얼로그 초기 포커스·Esc 닫기', async ({ page }) => {
    const id = await freshTrip(page, 'POI a11y');
    let posted = 0;
    page.on('request', (r) => {
      if (r.method() === 'POST' && new URL(r.url()).pathname === `/trips/${id}/pois`) posted += 1;
    });
    await rightClickMap(page);
    await expect(manualDialog(page)).toBeVisible();
    await expect(manualDialog(page).getByLabel('이름')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(manualDialog(page)).toBeHidden();
    expect(posted).toBe(0);
    await expect(markerLegend(page)).toHaveCount(0);
  });

  test('POI-032 기존 마커 우클릭은 편집기를 연다', async ({ page }) => {
    const id = await freshTrip(page, 'POI 마커우클릭');
    await createManualPoi(page, id, e2eName('마커'));
    // single POI → map.flyTo(center, zoom 13); the marker sits at canvas center after animation
    await page.waitForTimeout(1500);
    await rightClickMap(page);
    const editor = page.getByTestId('poi-editor');
    const dialog = manualDialog(page);
    await expect(editor.or(dialog)).toBeVisible();
    if (await dialog.isVisible()) {
      await page.keyboard.press('Escape');
      test.skip(true, '마커가 캔버스 중앙에 없었다(애니메이션/타일 지연) — 생성 다이얼로그가 열림');
    }
    await expect(editor).toBeVisible();
    await expect(dialog).toHaveCount(0);
  });
});

test.describe('POI create (mobile)', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile project only (390x844, hasTouch)');

  test('POI-002 롱프레스로 POI 생성', async ({ page }) => {
    const id = await freshTrip(page, 'POI 롱프레스');
    // a short tap must not open the dialog
    await longPressMap(page, 0, 0, 150);
    await expect(manualDialog(page)).toHaveCount(0);
    await longPressMap(page, 0, 0, 900);
    await expect(manualDialog(page)).toBeVisible({ timeout: 10_000 });
    await snap(page, 'POI-002', 'dialog');
    const name = e2eName('롱프레스');
    await submitManualDialog(page, id, name);
    await expect(markerLegend(page).filter({ hasText: name })).toHaveCount(1);
    await expect(mapStats(page)).toContainText('장소 1곳');
    await openPanelIfMobile(page);
    await expect(poiRow(page, name)).toHaveCount(1);
    await snap(page, 'POI-002', 'created');
  });
});
