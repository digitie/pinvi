/**
 * TRIP-029 … TRIP-036 — place operations inside a day: 1..8 adds, drag reorder, delete,
 * per-place memo, kakao add notice, trip copy (복사) and rename.
 */
import { expect, test } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  loginAsUser,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
  waitForRequest,
} from '../../helpers/live';
import {
  copyTripViaUi,
  dayTab,
  deletePoi,
  dragPoi,
  e2eTitle,
  gotoTrip,
  isoDate,
  mapMarkers,
  openTripEdit,
  poiRows,
  poiTitles,
  preferFeature,
  preferKakao,
  saveTripEdit,
  selectDay,
  setPoiNote,
  summaryPattern,
  tripListCard,
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

// Seoul mix across families; 8 distinct, stable places.
const SEOUL_EIGHT: { query: string; family: string }[] = [
  { query: '경복궁', family: 'heritage' },
  { query: '창덕궁', family: 'heritage' },
  { query: '국립중앙박물관', family: 'museum' },
  { query: '남산공원', family: 'park' },
  { query: '서울역', family: 'transport' },
  { query: '덕수궁', family: 'heritage' },
  { query: '서울숲', family: 'park' },
  { query: '국립민속박물관', family: 'museum' },
];

test('[TRIP-029] 한 일자에 장소 8개 추가 — 순번 1..8, 헤더 8개, 비활성 일자 미리보기 "외 4곳"', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('8곳'), start: isoDate(12), end: isoDate(13), region: '서울' });
  created.push(id);
  await gotoTrip(page, id);

  const names: string[] = [];
  for (const p of SEOUL_EIGHT) names.push(await searchAndAddPlace(page, 1, p.query, preferFeature));

  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(8);
  const titles = await poiTitles(page);
  expect(titles.map((t) => t.slice(0, 4))).toEqual(names.map((n) => n.slice(0, 4)));
  await expect(dayTab(page, '1일차')).toContainText('8곳');
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(2, 8));
  await waitForMapIdle(page);
  await expect(mapMarkers(page)).toHaveCount(8);
  await shot(page, 'TRIP-029', 'eight');

  // collapsed preview of a non-active day shows at most 4 + "외 N곳"
  await selectDay(page, '2일차');
  await expect(page.getByTestId('trip-layer-list')).toContainText('외 4곳');
});

test('[TRIP-030] 드래그로 순서 변경 — 3번째를 1번째로, 새로고침 후에도 유지', async ({ page }, testInfo) => {
  test.skip(testInfo.project.use.hasTouch === true, 'HTML5 drag needs a mouse pointer; mobile reorder is manual (TRIP-050)');
  const { id } = await createTrip(page, { title: e2eTitle('순서'), start: isoDate(12), end: isoDate(12), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  const a = await searchAndAddPlace(page, 1, '불국사', preferFeature);
  const b = await searchAndAddPlace(page, 1, '석굴암', preferFeature);
  const c = await searchAndAddPlace(page, 1, '첨성대', preferFeature);
  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(3);

  const reorder = waitForRequest(page, /\/trips\/[0-9a-f-]{36}\/pois\/reorder/);
  await dragPoi(page, 2, 0);
  const res = await reorder;
  expect(res.ok()).toBeTruthy();

  await expect.poll(async () => (await poiTitles(page)).map((t) => t.slice(0, 3))).toEqual(
    [c, a, b].map((n) => n.slice(0, 3)),
  );
  await shot(page, 'TRIP-030', 'reordered');

  await gotoTrip(page, id);
  await selectDay(page, '1일차');
  await expect.poll(async () => (await poiTitles(page)).map((t) => t.slice(0, 3))).toEqual(
    [c, a, b].map((n) => n.slice(0, 3)),
  );
});

test('[TRIP-031] 장소 삭제 — 행·헤더·마커가 함께 줄고 순번이 재계산된다', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('장소삭제'), start: isoDate(12), end: isoDate(12), region: '안동' });
  created.push(id);
  await gotoTrip(page, id);

  const first = await searchAndAddPlace(page, 1, '안동하회마을', preferFeature);
  const second = await searchAndAddPlace(page, 1, '도산서원', preferFeature);
  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(2);
  await waitForMapIdle(page);
  await expect(mapMarkers(page)).toHaveCount(2);

  await deletePoi(page, 0);
  await expect(poiRows(page).first()).toContainText(second.slice(0, 4));
  await expect(poiRows(page).first()).not.toContainText(first.slice(0, 4));
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(1, 1));
  await expect(mapMarkers(page)).toHaveCount(1);
  await shot(page, 'TRIP-031', 'after-delete');
});

test('[TRIP-032] 장소별 메모 — 편집기에서 저장하면 행에 표시되고 새로고침 후 유지', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('메모'), start: isoDate(12), end: isoDate(12), region: '영월' });
  created.push(id);
  await gotoTrip(page, id);

  await searchAndAddPlace(page, 1, '고씨굴', preferFeature); // natural/heritage cave
  await selectDay(page, '1일차');
  await expect(poiRows(page)).toHaveCount(1);

  const note = `[e2e] 입장권 현장 구매 ${Date.now().toString(36)}`;
  await setPoiNote(page, 0, note);
  await expect(poiRows(page).first()).toContainText(note);
  await shot(page, 'TRIP-032', 'note');

  await gotoTrip(page, id);
  await selectDay(page, '1일차');
  await expect(poiRows(page).first()).toContainText(note);
});

test('[TRIP-033] 카카오 결과 추가 — 안내 문구와 외부 소스 행 표시', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('카카오'), start: isoDate(12), end: isoDate(12), region: '부산' });
  created.push(id);
  await gotoTrip(page, id);

  const name = await searchAndAddPlace(page, 1, '해운대 횟집', preferKakao); // food via kakao
  await selectDay(page, '1일차');
  await expect(page.getByTestId('poi-add-notice')).toContainText(
    '카카오 장소를 추가했어요. 상세 정보는 준비되는 대로 표시됩니다.',
  );
  await expect(poiRows(page).first()).toContainText(name.slice(0, 4));
  await shot(page, 'TRIP-033', 'kakao-notice');
});

test('[TRIP-034] 여행 복사(복사) — "<제목> copy" 새 초안, 일자·장소·메모가 그대로', async ({ page }) => {
  const title = e2eTitle('원본');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(13), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);
  const a = await searchAndAddPlace(page, 1, '불국사', preferFeature);
  const b = await searchAndAddPlace(page, 2, '첨성대', preferFeature);
  await selectDay(page, '1일차');
  await setPoiNote(page, 0, '[e2e] copy-check');

  const copyId = await copyTripViaUi(page, id);
  created.push(copyId);
  await expect(page.getByRole('heading', { name: `${title} copy` }).first()).toBeVisible();
  await expect(page.getByTestId('trip-top-panel')).toContainText('초안');
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(2, 2));
  await selectDay(page, '1일차');
  await expect(poiRows(page).first()).toContainText(a.slice(0, 4));
  await expect(poiRows(page).first()).toContainText('[e2e] copy-check');
  await selectDay(page, '2일차');
  await expect(poiRows(page).first()).toContainText(b.slice(0, 4));
  await shot(page, 'TRIP-034', 'copy');

  // the source is untouched
  await gotoTrip(page, id);
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(2, 2));
  await page.goto('/trips');
  await expect(tripListCard(page, `${title} copy`)).toBeVisible();
  await expect(tripListCard(page, title)).toHaveCount(2); // original + copy (prefix match)
});

test('[TRIP-035] 여행 이름 변경 — 헤더와 목록 카드에 반영, 지역도 함께', async ({ page }) => {
  const title = e2eTitle('이름전');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12), region: '서울' });
  created.push(id);
  await gotoTrip(page, id);

  const next = `${title} 이름후`;
  await openTripEdit(page);
  await page.locator('#trip-edit-title').fill(next);
  await page.locator('#trip-edit-region').fill('부산');
  await saveTripEdit(page);
  await expect(page.getByRole('heading', { name: next }).first()).toBeVisible();
  await expect(page.getByTestId('trip-top-panel')).toContainText('부산');

  await page.goto('/trips');
  await expect(tripListCard(page, next)).toBeVisible();
  await expect(tripListCard(page, next)).toContainText('부산');
  await shot(page, 'TRIP-035', 'renamed-list');
});

test('[TRIP-036] 제목만 비우면 저장 버튼이 비활성 — 빈 제목으로 PATCH 불가', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('빈제목'), start: isoDate(12), end: isoDate(12) });
  created.push(id);
  await gotoTrip(page, id);
  await openTripEdit(page);
  await page.locator('#trip-edit-title').fill('   ');
  await expect(page.getByTestId('trip-edit-save')).toBeDisabled();
  await page.getByRole('button', { name: '취소', exact: true }).click();
});
