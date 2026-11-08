/**
 * Area-local helpers for the TRIP live specs. Everything here is derived from the PinVi web
 * source (apps/web) so selectors match the deployed UI — see README.md "Source references".
 *
 * Cross-area helpers (login, createTrip, deleteTrip, searchAndAddPlace, shot …) come from
 * `../helpers/live` (integrator-supplied). This file only adds trip-detail specifics.
 */
import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import { closePanel, dayTab, detailPanel, e2eTitle, isMobile, isoDate, openPanel, poiRows, revealCreateForm, tripIdFromUrl } from './live';

export { dayTab, detailPanel, e2eTitle, isMobile, isoDate, openPanel, poiRows, revealCreateForm, tripIdFromUrl };

/** Mirrors `formatTripDate` in packages/domain/src/tripDateLabels.ts → "2026년 11월 5일". */
export function koDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return `${y}년 ${m}월 ${d}일`;
}

/** Header summary — desktop `N일 · M개 장소`, mobile `N일 · M곳` (TripDetail.tsx). */
export function summaryPattern(days: number, pois: number): RegExp {
  return new RegExp(`${days}일 · ${pois}(개 장소|곳)`);
}

/* --------------------------------------------------------- detail page */

export async function closePanelIfMobile(page: Page, testInfo: TestInfo): Promise<void> {
  if (!isMobile(testInfo)) return;
  await closePanel(page);
}

/** Selects a day tab by its label ('1일차' or a renamed title) — the shared `selectDay` takes a number. */
export async function selectDay(page: Page, label: string): Promise<void> {
  await openPanel(page);
  await dayTab(page, label).click();
  await expect(dayTab(page, label)).toHaveAttribute('aria-selected', 'true');
}

/** Add-day button: desktop header `trip-add-layer`, mobile drawer `trip-add-day-drawer`. */
export function addDayButton(page: Page, testInfo: TestInfo): Locator {
  return isMobile(testInfo)
    ? page.getByTestId('trip-add-day-drawer')
    : page.getByTestId('trip-add-layer');
}

/** The `trip-top-panel` (desktop) or the drawer header (mobile) carries the add-day disabled reason. */
export function addDayReasonHost(page: Page, testInfo: TestInfo): Locator {
  return isMobile(testInfo) ? detailPanel(page) : page.getByTestId('trip-top-panel');
}

export async function addDay(page: Page, testInfo: TestInfo, expectLabel: string): Promise<void> {
  if (isMobile(testInfo)) await openPanel(page);
  const btn = addDayButton(page, testInfo);
  await expect(btn).toBeEnabled();
  await btn.click();
  await expect(dayTab(page, expectLabel)).toBeVisible();
}

export function dayDeleteButton(page: Page, dayIndex: number): Locator {
  return page.getByRole('button', { name: `${dayIndex}일차 삭제`, exact: true });
}

export function daySettingsButton(page: Page, dayIndex: number): Locator {
  return page.getByRole('button', { name: `${dayIndex}일차 설정`, exact: true });
}

export function dayVisibilityCheckbox(page: Page, dayLabel: string): Locator {
  return page.getByRole('checkbox', { name: `${dayLabel} 표시`, exact: true });
}

/** Visible title of a POI row (first line of the select button). */
export async function poiTitle(row: Locator): Promise<string> {
  // The select button starts with an aria-hidden ordinal badge ("1", "2", …); the name is the
  // `.truncate` span (TripPoiList.tsx `poi.title ?? poi.feature_id ?? '장소'`).
  const text = await row.locator('button[aria-current] span.truncate').first().innerText();
  return text.trim();
}

export async function poiTitles(page: Page): Promise<string[]> {
  const rows = poiRows(page);
  const count = await rows.count();
  const titles: string[] = [];
  for (let i = 0; i < count; i += 1) titles.push(await poiTitle(rows.nth(i)));
  return titles;
}

/** Map-side ground truth: one sr-only `trip-map-marker-style` span per rendered POI marker. */
export function mapMarkers(page: Page): Locator {
  return page.getByTestId('trip-map-marker-style');
}

export function mapStats(page: Page): Locator {
  return page.getByTestId('trip-map-stats');
}

/** HTML5 drag of POI row `from` onto row `to` (TripPoiList.tsx `draggable` li + onDrop). */
export async function dragPoi(page: Page, from: number, to: number): Promise<void> {
  // HTML5 drag events go straight to the source/target rows. `locator.dragTo` presses the mouse on the
  // source and then scrolls the target into view; in the scrollable plan panel (#705) the scroll moves a
  // different row under the pointer before `dragstart`, so a long list dragged row 1 instead of the last
  // one (TRS 2026-11-08: '공화춘↔짜장면박물관' swapped, reorder 200).
  const rows = poiRows(page);
  const source = rows.nth(from);
  const target = rows.nth(to);
  await source.scrollIntoViewIfNeeded();
  const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent('dragstart', { dataTransfer });
  await target.scrollIntoViewIfNeeded();
  await target.dispatchEvent('dragover', { dataTransfer });
  await target.dispatchEvent('drop', { dataTransfer });
  await source.dispatchEvent('dragend', { dataTransfer });
  await dataTransfer.dispose();
}

/** Opens the inline PoiEditor for row `index` and sets the 메모 field. */
export async function setPoiNote(page: Page, index: number, note: string): Promise<void> {
  const row = poiRows(page).nth(index);
  await row.getByRole('button', { name: '마커 편집' }).click();
  const editor = page.getByTestId('poi-editor');
  await expect(editor).toBeVisible();
  await editor.locator('#poi-edit-note').fill(note);
  await editor.getByRole('button', { name: '저장', exact: true }).click();
  await expect(editor).toHaveCount(0);
}

export async function deletePoi(page: Page, index: number): Promise<void> {
  const before = await poiRows(page).count();
  await poiRows(page).nth(index).getByRole('button', { name: '장소 삭제' }).click();
  await expect(poiRows(page)).toHaveCount(before - 1);
}

/* ------------------------------------------------------ trip-level actions */

/** '편집' button lives in the desktop header or the mobile drawer header. */
export async function openTripEdit(page: Page): Promise<Locator> {
  await openPanel(page);
  await page.getByRole('button', { name: '편집', exact: true }).first().click();
  const dialog = page.getByTestId('trip-edit-dialog');
  await expect(dialog).toBeVisible();
  return dialog;
}

export async function saveTripEdit(page: Page): Promise<void> {
  await page.getByTestId('trip-edit-save').click();
  await expect(page.getByTestId('trip-edit-dialog')).toHaveCount(0);
}

/** Desktop header `TripActions` or mobile drawer `TripActions` — same labels. */
export function tripActions(page: Page): Locator {
  return page.getByTestId('trip-actions').first();
}

/** '복사' → navigates to the new trip; returns its id. */
export async function copyTripViaUi(page: Page, sourceId: string): Promise<string> {
  await openPanel(page);
  await tripActions(page).getByRole('button', { name: '복사', exact: true }).click();
  await expect(page).toHaveURL(/\/trips\/[0-9a-f-]{36}/i);
  await expect.poll(() => tripIdFromUrl(page)).not.toBe(sourceId);
  return tripIdFromUrl(page);
}

/** '삭제' → '삭제 확인' → back on /trips. */
export async function deleteTripViaUi(page: Page): Promise<void> {
  await openPanel(page);
  await tripActions(page).getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByTestId('trip-delete-confirm').click();
  await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/);
}

export async function gotoTrip(page: Page, id: string): Promise<void> {
  await page.goto(`/trips/${id}`);
  await expect(page.getByTestId('trip-detail-shell')).toBeVisible();
}

/* ------------------------------------------------------------ dashboard */

export function tripListCard(page: Page, title: string): Locator {
  return page.getByTestId('trip-list').getByRole('link').filter({ hasText: title });
}

export function bucketButton(page: Page, label: '예정' | '지난 여행'): Locator {
  return page.getByRole('group', { name: '여행 필터' }).getByRole('button', { name: label });
}

/** Search-result picker: prefer a Map feature row (badge '장소') over kakao/naver/address rows. */
export const preferFeature = (rowText: string): boolean =>
  rowText.includes('장소') && !rowText.includes('카카오') && !rowText.includes('네이버');
export const preferKakao = (rowText: string): boolean => rowText.includes('카카오');
export const preferExternal = (rowText: string): boolean =>
  rowText.includes('카카오') || rowText.includes('네이버');
