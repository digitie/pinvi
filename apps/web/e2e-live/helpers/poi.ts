/**
 * Area-local helpers for the `poi` live suite (my-POI creation + attachments).
 * Shared helpers come from `../helpers/live` (integrator-supplied); nothing here
 * touches the network except through the real PinVi UI.
 *
 * Selector sources (PinVi main a07257e7):
 *  - apps/web/components/trips/TripMapView.tsx       trip-map-surface, trip-map-marker-style, trip-map-detail-open
 *  - apps/web/components/trips/TripManualPoiDialog.tsx manual-poi-dialog, manual-poi-address, manual-poi-submit, label '이름'
 *  - apps/web/components/trips/TripDetail.tsx         trip-detail-panel, trip-map-place-search, trip-map-stats, poi-mutation-error, poi-add-notice, tabs '일정/파일/…', day tabs 'N일차'
 *  - apps/web/components/trips/TripPoiList.tsx        trip-poi-list, '마커 편집', '장소 삭제'
 *  - apps/web/components/trips/TripAttachments.tsx    attachment-input, trip-attachment-list, trip-attachment-toggle, '다운로드', '삭제', '파일 없음'
 *  - apps/web/components/map/MapSearchBox.tsx         map-search, label '장소·주소 검색', map-search-result-<source>, alert '검색 결과가 없습니다.'
 *  - apps/web/app/(app)/files/page.tsx                my-file-list, file-delete-confirm, '다운로드', '삭제'
 */
import { expect, type Locator, type Page } from '@playwright/test';
import { closePanel, e2ePrefix, isMobileProject, openPanel, shot, waitForMapIdle } from './live';

export { isMobileProject };

export const JPEG_BYTES = Buffer.from([0xff, 0xd8, 0xff, 0xd9]);
export const PNG_BYTES = Buffer.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
]);
export const PDF_BYTES = Buffer.from('%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n');

export function stamp(): string {
  return `${Date.now().toString(36)}`;
}

export function e2eName(label: string): string {
  return `${e2ePrefix} ${label} ${stamp()}`;
}

export function e2eFileName(label: string, ext: string): string {
  // '[e2e]' prefix lives in the filename so the /files sweep can find leftovers.
  return `${e2ePrefix}-${label}-${stamp()}.${ext}`;
}

/** Open a trip detail page and wait until the MapLibre canvas is up and tiles have settled. */
export async function gotoTrip(page: Page, tripId: string): Promise<void> {
  await page.goto(`/trips/${tripId}`);
  await expect(page.getByTestId('trip-detail-map')).toBeVisible();
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible({ timeout: 30_000 });
  await waitForMapIdle(page);
}

/** On the mobile layout the side panel starts hidden; open it when needed. */
export async function openPanelIfMobile(page: Page): Promise<void> {
  if (!isMobileProject()) return;
  await openPanel(page);
}

export async function closePanelIfMobile(page: Page): Promise<void> {
  if (!isMobileProject()) return;
  await closePanel(page);
}

/** Select day N in the plan panel (role=tab, aria-label `${n}일차`). */
export async function selectDay(page: Page, dayIndex: number): Promise<void> {
  await openPanelIfMobile(page);
  const planTab = page.getByRole('tab', { name: '일정' });
  if ((await planTab.count()) > 0 && (await planTab.first().getAttribute('aria-selected')) !== 'true') {
    await planTab.first().click();
  }
  const dayTab = page.getByRole('tab', { name: `${dayIndex}일차`, exact: true });
  await expect(dayTab).toBeVisible();
  if ((await dayTab.getAttribute('aria-selected')) !== 'true') await dayTab.click();
  await expect(dayTab).toHaveAttribute('aria-selected', 'true');
}

/** The day-tab badge text, e.g. '1곳'. */
export function dayBadge(page: Page, dayIndex: number): Locator {
  return page.getByRole('tab', { name: `${dayIndex}일차`, exact: true }).locator('span', {
    hasText: /^\d+곳$/,
  });
}

export function mapStats(page: Page): Locator {
  return page.getByTestId('trip-map-stats');
}

export function markerLegend(page: Page): Locator {
  return page.locator('[data-testid="trip-map-marker-style"]');
}

export function poiList(page: Page): Locator {
  return page.getByTestId('trip-poi-list');
}

export function poiRow(page: Page, title: string): Locator {
  return poiList(page).getByRole('listitem').filter({ hasText: title });
}

/** The search box overlaid on the map (there is a second one inside the day panel). */
export function mapSearchInput(page: Page): Locator {
  return page.getByTestId('trip-map-place-search').getByLabel('장소·주소 검색');
}

export function mapSearchContainer(page: Page): Locator {
  return page.getByTestId('trip-map-place-search');
}

async function canvasCenter(page: Page): Promise<{ x: number; y: number; w: number; h: number }> {
  const canvas = page.locator('.maplibregl-canvas').first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('maplibre canvas has no bounding box');
  return { x: box.x + box.width / 2, y: box.y + box.height / 2, w: box.width, h: box.height };
}

/**
 * Right-click the map at (center + offset) to open the manual POI dialog.
 * TripMapView.handleMouseDown (button===2) → onCreatePoiAtCoordinate → TripManualPoiDialog.
 */
export async function rightClickMap(page: Page, dx = 0, dy = 0): Promise<void> {
  await closePanelIfMobile(page);
  const c = await canvasCenter(page);
  await page.mouse.click(c.x + dx, c.y + dy, { button: 'right' });
}

/**
 * Long-press the map on a touch project: dispatch a real TouchEvent pair held > 650 ms
 * (TripMapView.handleTouchStart timer). Playwright's touchscreen.tap has no hold.
 */
export async function longPressMap(page: Page, dx = 0, dy = 0, holdMs = 900): Promise<void> {
  await closePanelIfMobile(page);
  const c = await canvasCenter(page);
  const x = c.x + dx;
  const y = c.y + dy;
  await page.evaluate(
    ({ x, y, holdMs }) =>
      new Promise<void>((resolve) => {
        const el = document.elementFromPoint(x, y) as HTMLElement | null;
        if (!el) throw new Error('no element under long-press point');
        const mk = (type: string, withTouches: boolean) => {
          const touch = new Touch({ identifier: 7, target: el, clientX: x, clientY: y, pageX: x, pageY: y });
          return new TouchEvent(type, {
            bubbles: true,
            cancelable: true,
            composed: true,
            touches: withTouches ? [touch] : [],
            targetTouches: withTouches ? [touch] : [],
            changedTouches: [touch],
          });
        };
        el.dispatchEvent(mk('touchstart', true));
        setTimeout(() => {
          el.dispatchEvent(mk('touchend', false));
          resolve();
        }, holdMs);
      }),
    { x, y, holdMs },
  );
}

export function manualDialog(page: Page): Locator {
  return page.getByTestId('manual-poi-dialog');
}

/** Wait until reverse-geocoding finished and return the address text ('주소 결과 없음' when none). */
export async function waitForDialogAddress(page: Page): Promise<string> {
  const address = page.getByTestId('manual-poi-address');
  await expect(address).toBeVisible();
  await expect(address).not.toHaveText('주소 확인 중…', { timeout: 20_000 });
  await expect(address).not.toHaveAttribute('aria-busy', 'true');
  return (await address.textContent())?.trim() ?? '';
}

/**
 * Fill the open manual-POI dialog and submit. Returns the created POI's title
 * (the address label when `name` is null) and the POST body the UI sent.
 */
export async function submitManualDialog(
  page: Page,
  tripId: string,
  name: string | null,
): Promise<{ title: string; body: Record<string, unknown>; poiId: string }> {
  const address = await waitForDialogAddress(page);
  const input = manualDialog(page).getByLabel('이름');
  await input.fill(name ?? '');
  const title = name ?? address;
  const responsePromise = page.waitForResponse(
    (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === `/trips/${tripId}/pois`,
  );
  await page.getByTestId('manual-poi-submit').click();
  const response = await responsePromise;
  expect(response.status(), 'POST /pois').toBe(201);
  const body = response.request().postDataJSON() as Record<string, unknown>;
  const json = (await response.json()) as { data: { attachment_id: string } };
  await expect(manualDialog(page)).toBeHidden();
  await openPanelIfMobile(page); // the POI list lives in the (closed) mobile drawer
  await expect(poiRow(page, title).first()).toBeVisible();
  return { title, body, poiId: json.data.attachment_id };
}

/** Right-click → dialog → create; one-call convenience used by most cases. */
export async function createManualPoi(
  page: Page,
  tripId: string,
  name: string,
  offset: { dx?: number; dy?: number } = {},
): Promise<{ title: string; body: Record<string, unknown>; poiId: string }> {
  await rightClickMap(page, offset.dx ?? 0, offset.dy ?? 0);
  await expect(manualDialog(page)).toBeVisible();
  const created = await submitManualDialog(page, tripId, name);
  await openPanelIfMobile(page);
  return created;
}

/** Delete every POI row still visible in the selected day (only used on `[e2e]` trips). */
export async function deleteAllPoisInDay(page: Page): Promise<void> {
  await openPanelIfMobile(page);
  const buttons = page.getByRole('button', { name: '장소 삭제' });
  for (let guard = 0; guard < 50 && (await buttons.count()) > 0; guard += 1) {
    await buttons.first().click();
    await page.waitForTimeout(250);
  }
  await expect(buttons).toHaveCount(0);
}

/** Type in the map search box and wait for the GET /search response. */
export async function searchPlaces(page: Page, query: string): Promise<void> {
  const input = mapSearchInput(page);
  await input.fill('');
  const responsePromise = page.waitForResponse(
    (r) => r.request().method() === 'GET' && new URL(r.url()).pathname === '/search',
    { timeout: 30_000 },
  );
  await input.fill(query);
  await responsePromise;
}

/** Pick the first search row of `source` whose text matches `match`; returns the row text. */
export async function pickSearchRow(
  page: Page,
  tripId: string,
  source: 'feature' | 'address' | 'my_poi' | 'kakao' | 'naver',
  match?: RegExp,
): Promise<{ rowText: string; body: Record<string, unknown> }> {
  let rows = mapSearchContainer(page).getByTestId(`map-search-result-${source}`);
  if (match) rows = rows.filter({ hasText: match });
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  const rowText = (await rows.first().textContent()) ?? '';
  const responsePromise = page.waitForResponse(
    (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === `/trips/${tripId}/pois`,
  );
  await rows.first().click();
  const response = await responsePromise;
  expect(response.status(), 'POST /pois').toBe(201);
  return { rowText, body: response.request().postDataJSON() as Record<string, unknown> };
}

/** `<section aria-label="첨부">` that carries the given heading (e.g. '1일차 파일', '첨부'). */
export function attachmentSection(page: Page, heading: string): Locator {
  return page
    .locator('section[aria-label="첨부"]')
    .filter({ has: page.getByRole('heading', { name: heading, exact: true }) });
}

/** The trip-scope section in the '파일' tab is the last one rendered (TripDetail.tsx 1859). */
export async function openFilesTab(page: Page): Promise<Locator> {
  await openPanelIfMobile(page);
  await page.getByRole('tab', { name: '파일' }).click();
  await expect(page.getByRole('heading', { name: '첨부', exact: true })).toBeVisible();
  return attachmentSection(page, '첨부');
}

export async function uploadTo(
  section: Locator,
  file: { name: string; mimeType: string; buffer: Buffer },
): Promise<Locator> {
  await section.getByTestId('attachment-input').setInputFiles(file);
  const row = section.getByTestId('trip-attachment-list').getByRole('listitem').filter({
    hasText: file.name,
  });
  await expect(row).toBeVisible({ timeout: 45_000 });
  return row;
}

export async function deleteAttachmentRow(row: Locator): Promise<void> {
  await row.getByRole('button', { name: '삭제' }).click();
  await expect(row).toHaveCount(0);
}

/** Replace window.open so download clicks are observable without a popup. */
export async function stubWindowOpen(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'open', {
      value: (url: string | URL | undefined) => {
        (window as Window & { __e2eOpenedUrl?: string }).__e2eOpenedUrl = String(url);
        return null;
      },
    });
  });
}

export async function lastOpenedUrl(page: Page): Promise<string> {
  await expect
    .poll(() => page.evaluate(() => (window as Window & { __e2eOpenedUrl?: string }).__e2eOpenedUrl ?? ''))
    .not.toBe('');
  return page.evaluate(() => (window as Window & { __e2eOpenedUrl?: string }).__e2eOpenedUrl ?? '');
}

/**
 * Delete every `/files` row whose filename carries the e2e prefix (ConfirmDialog
 * testId=file-delete-confirm). Returns how many were removed. Loops because the
 * page shows the most recent 100 only.
 */
export async function sweepE2eFiles(page: Page): Promise<number> {
  let removed = 0;
  for (let round = 0; round < 10; round += 1) {
    await page.goto('/files');
    await expect(page.getByRole('heading', { name: '파일' })).toBeVisible();
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 20_000 });
    // Match on the filename cell only (the row also shows trip/POI context text), anchored at the start.
    const rows = page
      .getByTestId('my-file-list')
      .getByRole('listitem')
      .filter({ has: page.locator('span.font-semibold', { hasText: /^\s*\[e2e\]/ }) });
    const count = await rows.count();
    if (count === 0) return removed;
    for (let i = 0; i < count; i += 1) {
      const row = rows.first();
      const fileName = ((await row.locator('span.font-semibold').first().textContent()) ?? '').trim();
      if (!fileName.startsWith(e2ePrefix)) throw new Error('sweepE2eFiles: refusing to delete a non-[e2e] file');
      await row.getByRole('button', { name: '삭제' }).click();
      const dialog = page.getByTestId('file-delete-confirm');
      await expect(dialog).toBeVisible();
      await dialog.getByRole('button', { name: '삭제' }).click();
      await expect(dialog).toBeHidden();
      removed += 1;
    }
  }
  return removed;
}

export async function snap(page: Page, id: string, step: string): Promise<void> {
  await shot(page, id, step);
}
