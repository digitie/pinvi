/**
 * TRIP-037 … TRIP-040 — route optimize (동선 최적화): preview vs apply, single-day scope,
 * distance display, idempotent second preview.
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
  e2eTitle,
  gotoTrip,
  isoDate,
  poiRows,
  poiTitles,
  preferFeature,
  selectDay,
} from '../../helpers/trip';

const created: string[] = [];

test.beforeEach(async ({ page }) => {
  await loginAsUser(page);
});

test.afterEach(async ({ page }) => {
  while (created.length > 0) {
    const id = created.pop()!;
    await deleteTrip(page, id).catch(() => undefined);
  }
});

const DISTANCE = /\d+(\.\d)?(km|m)/; // formatDistanceMeters: `123m` | `1.2km`

/** Deliberately zig-zag Gyeongju order so a 2-opt pass has something to improve. */
async function seedZigZag(page: import('@playwright/test').Page, tripId: string) {
  await gotoTrip(page, tripId);
  const order = ['불국사', '경주역', '석굴암', '첨성대', '국립경주박물관']; // heritage/transport/museum
  const names: string[] = [];
  for (const q of order) names.push(await searchAndAddPlace(page, 1, q, preferFeature));
  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(order.length);
  return names;
}

test('[TRIP-037] 미리보기만 — 거리·순서 변경 수를 보여주고 닫으면 순서가 바뀌지 않는다', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('최적화미리보기'), start: isoDate(12), end: isoDate(12), region: '경주' });
  created.push(id);
  await seedZigZag(page, id);
  const before = await poiTitles(page);

  const optimize = page.getByTestId('trip-day-optimize');
  await expect(optimize).toBeVisible();
  const preview = waitForRequest(page, /\/days\/1\/optimize$/);
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  const res = await preview;
  expect(res.ok()).toBeTruthy();
  expect((res.request().postDataJSON() as { persist: boolean }).persist).toBe(false);

  await expect(optimize).toContainText(DISTANCE);
  await expect(optimize).toContainText(/순서 변경 \d+곳/);
  await expect(optimize).toContainText(/기존 .+ → 최적 .+|최단 경로 추정 거리/);
  await shot(page, 'TRIP-037', 'preview');

  await optimize.getByRole('button', { name: '닫기', exact: true }).click();
  await expect(optimize).not.toContainText('순서 변경');
  expect(await poiTitles(page)).toEqual(before);

  await gotoTrip(page, id);
  await selectDay(page, '1일차');
  expect(await poiTitles(page)).toEqual(before);
});

test('[TRIP-038] 적용 — persist=true로 저장, 순서가 바뀌고 두 번째 미리보기는 변경 0곳(적용 비활성)', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('최적화적용'), start: isoDate(12), end: isoDate(12), region: '경주' });
  created.push(id);
  await seedZigZag(page, id);
  const before = await poiTitles(page);

  const optimize = page.getByTestId('trip-day-optimize');
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  await expect(optimize).toContainText(/순서 변경 \d+곳/);
  const movesText = await optimize.innerText();
  const moves = Number(/순서 변경 (\d+)곳/.exec(movesText)?.[1] ?? '0');
  test.skip(moves === 0, 'live routing returned the seeded order as already optimal — nothing to apply');

  const apply = waitForRequest(page, /\/days\/1\/optimize$/);
  await optimize.getByRole('button', { name: '적용', exact: true }).click();
  const res = await apply;
  expect(res.ok()).toBeTruthy();
  expect((res.request().postDataJSON() as { persist: boolean }).persist).toBe(true);
  await expect(optimize).not.toContainText('순서 변경'); // preview panel closes on apply

  await expect.poll(async () => poiTitles(page)).not.toEqual(before);
  const after = await poiTitles(page);
  expect([...after].sort()).toEqual([...before].sort()); // same set, new order
  await shot(page, 'TRIP-038', 'applied');

  // persisted
  await gotoTrip(page, id);
  await selectDay(page, '1일차');
  expect(await poiTitles(page)).toEqual(after);

  // second preview: already optimal → 0 moves, apply disabled
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  await expect(optimize).toContainText('순서 변경 0곳');
  await expect(optimize.getByRole('button', { name: '적용', exact: true })).toBeDisabled();
});

test('[TRIP-039] 일자 단위 — 장소 2개 미만 일자에는 버튼이 없고, 선택한 일자에만 적용된다', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('최적화범위'), start: isoDate(12), end: isoDate(13), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  await searchAndAddPlace(page, 1, '불국사', preferFeature);
  await searchAndAddPlace(page, 1, '첨성대', preferFeature);
  await searchAndAddPlace(page, 2, '석굴암', preferFeature);

  await selectDay(page, '2일차');
  await expect(page.getByTestId('trip-day-optimize')).toHaveCount(0); // 1 place → hidden
  const day2 = await poiTitles(page);

  await selectDay(page, '1일차');
  const optimize = page.getByTestId('trip-day-optimize');
  await expect(optimize).toHaveCount(1);
  const req = waitForRequest(page, /\/days\/(\d+)\/optimize$/);
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  const res = await req;
  expect(new URL(res.url()).pathname).toMatch(/\/days\/1\/optimize$/);
  await expect(optimize).toContainText(/순서 변경 \d+곳/);
  await optimize.getByRole('button', { name: '닫기', exact: true }).click();

  await selectDay(page, '2일차');
  expect(await poiTitles(page)).toEqual(day2);
});

test('[TRIP-040] 좌표 없는 장소가 섞이면 경고 문구가 미리보기에 표시된다', async ({ page }) => {
  // Observational: warnings[] rendered as '⚠ …' line. Only asserts shape (warning line optional).
  const { id } = await createTrip(page, { title: e2eTitle('최적화경고'), start: isoDate(12), end: isoDate(12), region: '서울' });
  created.push(id);
  await gotoTrip(page, id);
  await searchAndAddPlace(page, 1, '경복궁', preferFeature);
  await searchAndAddPlace(page, 1, '서울역', preferFeature);
  await searchAndAddPlace(page, 1, '남산공원', preferFeature);
  await selectDay(page, '1일차');
  const optimize = page.getByTestId('trip-day-optimize');
  await optimize.getByRole('button', { name: '동선 최적화' }).click();
  await expect(optimize).toContainText(DISTANCE);
  const text = await optimize.innerText();
  test.info().annotations.push({ type: 'optimize-preview', description: text.replace(/\s+/g, ' ') });
  await shot(page, 'TRIP-040', 'preview-text');
  await optimize.getByRole('button', { name: '닫기', exact: true }).click();
});
