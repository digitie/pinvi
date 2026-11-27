/**
 * TRIP-072 … TRIP-074 — moving a place to another day (2026-11-27 소유자 요청: 같은 날짜 안에서만 되던
 * 끌어 놓기를 날짜끼리도). Drag onto a collapsed day, onto an empty day, and the keyboard step move that
 * crosses day boundaries. Every move is one `POST /trips/{id}/pois/{poi_id}/move`.
 *
 * Selectors: TripDetail.tsx (`trip-day-row` article + `data-drop-target`, tab '{N}일차' with 'N곳'),
 * TripPoiList.tsx (`trip-poi-list > li`, row button `button[aria-current]` with Alt+ArrowUp/Down).
 * Write-included (creates and deletes its own `[e2e]` trip) — run only against a non-production stack.
 */
import { expect, test } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  loginAsUser,
  searchAndAddPlace,
  shot,
  waitForRequest,
} from '../../helpers/live';
import {
  dayRow,
  dayTab,
  dragPoiToDay,
  e2eTitle,
  gotoTrip,
  isoDate,
  poiRows,
  poiTitles,
  preferFeature,
  selectDay,
} from '../../helpers/trip';

const MOVE = /\/trips\/[0-9a-f-]{36}\/pois\/[0-9a-f-]{36}\/move$/;
const created: string[] = [];

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.use.hasTouch === true, 'HTML5 drag and the grip keys need a desktop pointer/keyboard');
  await loginAsUser(page);
});

test.afterEach(async ({ page }) => {
  while (created.length > 0) {
    const id = created.pop()!;
    await deleteTrip(page, id).catch(() => undefined);
  }
});

const short = (titles: string[]) => titles.map((t) => t.slice(0, 6));

test('[TRIP-072] 장소를 접힌 다른 일자로 끌어 놓으면 그 일자 맨 끝으로 옮겨지고 새로고침 후에도 유지', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('일자이동'), start: isoDate(12), end: isoDate(13), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  const a = await searchAndAddPlace(page, 1, '불국사', preferFeature);
  const b = await searchAndAddPlace(page, 1, '석굴암', preferFeature);
  const c = await searchAndAddPlace(page, 2, '첨성대', preferFeature);

  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(2);
  const move = waitForRequest(page, MOVE);
  await dragPoiToDay(page, 0, 2);
  expect((await move).status()).toBe(200);

  await expect(dayTab(page, '1일차')).toContainText('1곳');
  await expect(dayTab(page, '2일차')).toContainText('2곳');
  await expect.poll(async () => short(await poiTitles(page))).toEqual(short([b]));
  await expect(page.getByTestId('poi-add-notice')).toContainText('2일차로 옮겼어요');
  await shot(page, 'TRIP-072', 'moved');

  await gotoTrip(page, id);
  await selectDay(page, '2일차');
  await expect.poll(async () => short(await poiTitles(page))).toEqual(short([c, a]));
});

test('[TRIP-073] 빈 일자에도 끌어 놓을 수 있다 — 그 일자의 첫 장소가 된다', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('빈일자'), start: isoDate(12), end: isoDate(14), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  await searchAndAddPlace(page, 1, '불국사', preferFeature);
  const b = await searchAndAddPlace(page, 1, '첨성대', preferFeature);
  await selectDay(page, '1일차');
  await expect(dayTab(page, '3일차')).toContainText('0곳');

  const move = waitForRequest(page, MOVE);
  await dragPoiToDay(page, 1, 3);
  const res = await move;
  expect(res.status()).toBe(200);
  const body = (await res.json()) as { data: { poi: { day_index: number }; from_day_index: number } };
  expect(body.data.from_day_index).toBe(1);
  expect(body.data.poi.day_index).toBe(3);

  await expect(dayTab(page, '1일차')).toContainText('1곳');
  await expect(dayTab(page, '3일차')).toContainText('1곳');
  await expect(dayRow(page, 3)).not.toHaveAttribute('data-drop-target', 'true');
  await selectDay(page, '3일차');
  await expect.poll(async () => short(await poiTitles(page))).toEqual(short([b]));
  await shot(page, 'TRIP-073', 'empty-day');
});

test('[TRIP-074] 장소 줄에서 Alt+아래 화살표 — 마지막 장소가 다음 일자 맨 앞으로, Alt+위로 되돌아온다', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('키보드이동'), start: isoDate(12), end: isoDate(13), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  const a = await searchAndAddPlace(page, 1, '불국사', preferFeature);
  const b = await searchAndAddPlace(page, 1, '석굴암', preferFeature);
  const c = await searchAndAddPlace(page, 2, '첨성대', preferFeature);

  await selectDay(page, '1일차');
  await poiRows(page).nth(1).locator('button[aria-current]').focus();
  const down = waitForRequest(page, MOVE);
  await page.keyboard.press('Alt+ArrowDown');
  expect((await down).status()).toBe(200);

  // 다음 일자가 펼쳐지고 옮긴 장소가 맨 앞, 초점은 그 장소 줄에 남는다.
  await expect(dayTab(page, '2일차')).toHaveAttribute('aria-selected', 'true');
  await expect.poll(async () => short(await poiTitles(page))).toEqual(short([b, c]));
  await expect(poiRows(page).first().locator('button[aria-current]')).toBeFocused();
  await shot(page, 'TRIP-074', 'keyboard-next-day');

  const up = waitForRequest(page, MOVE);
  await page.keyboard.press('Alt+ArrowUp');
  expect((await up).status()).toBe(200);
  await expect(dayTab(page, '1일차')).toHaveAttribute('aria-selected', 'true');
  await expect.poll(async () => short(await poiTitles(page))).toEqual(short([a, b]));
  await expect(poiRows(page).nth(1).locator('button[aria-current]')).toBeFocused();
});
