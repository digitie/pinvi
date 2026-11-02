/**
 * TRIP-001 … TRIP-011 — trip creation shapes, invalid dates, date change after places exist.
 * Live PROD, user account, every trip is `[e2e]`-prefixed and deleted in afterEach.
 */
import { expect, test } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  loginAsUser,
  searchAndAddPlace,
  shot,
} from '../../helpers/live';
import {
  addDayButton,
  addDayReasonHost,
  bucketButton,
  dayTab,
  e2eTitle,
  gotoTrip,
  isMobile,
  isoDate,
  koDate,
  openPanel,
  openTripEdit,
  poiRows,
  preferFeature,
  revealCreateForm,
  saveTripEdit,
  selectDay,
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

test('[TRIP-001] 당일 여행 생성 — 일자 1개, 일자 추가 불가 안내', async ({ page }, testInfo) => {
  const start = isoDate(7);
  const { id } = await createTrip(page, { title: e2eTitle('당일'), start, end: start, region: '서울' });
  created.push(id);
  await gotoTrip(page, id);
  await openPanel(page);

  await expect(dayTab(page, '1일차')).toBeVisible();
  await expect(dayTab(page, '2일차')).toHaveCount(0);
  await expect(page.getByTestId('trip-layer-list')).toContainText(koDate(start));
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(1, 0));
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(addDayReasonHost(page, testInfo)).toContainText(
    '여행 기간은 최대 1일입니다. 기간을 먼저 늘려주세요.',
  );
  await shot(page, 'TRIP-001', 'single-day');
});

test('[TRIP-002] 1박2일 여행 생성 — 일자 2개 자동 생성, 날짜 라벨', async ({ page }, testInfo) => {
  const start = isoDate(10);
  const end = isoDate(11);
  const { id } = await createTrip(page, { title: e2eTitle('1박2일'), start, end, region: '강릉' });
  created.push(id);
  await gotoTrip(page, id);
  await openPanel(page);

  await expect(dayTab(page, '1일차')).toBeVisible();
  await expect(dayTab(page, '2일차')).toBeVisible();
  await expect(dayTab(page, '3일차')).toHaveCount(0);
  const list = page.getByTestId('trip-layer-list');
  await expect(list).toContainText(koDate(start));
  await expect(list).toContainText(koDate(end));
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await shot(page, 'TRIP-002', 'two-days');
});

test('[TRIP-003] 3박4일 여행 생성 — 일자 4개, 목록 카드에 기간·초안 배지', async ({ page }) => {
  const start = isoDate(14);
  const end = isoDate(17);
  const title = e2eTitle('3박4일');
  const { id } = await createTrip(page, { title, start, end, region: '경주' });
  created.push(id);

  await page.goto('/trips');
  const card = tripListCard(page, title);
  await expect(card).toBeVisible();
  await expect(card).toContainText(`${koDate(start)} - ${koDate(end)}`);
  await expect(card).toContainText('초안');
  await expect(card).toContainText('경주');

  await gotoTrip(page, id);
  await openPanel(page);
  for (const n of [1, 2, 3, 4]) await expect(dayTab(page, `${n}일차`)).toBeVisible();
  await expect(dayTab(page, '5일차')).toHaveCount(0);
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(4, 0));
  await shot(page, 'TRIP-003', 'four-days');
});

test('[TRIP-004] 7일 여행 — 일자 7개, 기간 상한 7일 안내', async ({ page }, testInfo) => {
  const start = isoDate(20);
  const end = isoDate(26);
  const { id } = await createTrip(page, { title: e2eTitle('7일'), start, end, region: '제주' });
  created.push(id);
  await gotoTrip(page, id);
  await openPanel(page);

  for (let n = 1; n <= 7; n += 1) await expect(dayTab(page, `${n}일차`)).toBeVisible();
  await expect(dayTab(page, '8일차')).toHaveCount(0);
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(addDayReasonHost(page, testInfo)).toContainText('여행 기간은 최대 7일입니다.');
  await shot(page, 'TRIP-004', 'seven-days');
});

test('[TRIP-005] 날짜 없는 여행 — 일자 0개에서 "1일차 추가"로 미정 일자 생성', async ({ page }, testInfo) => {
  const { id } = await createTrip(page, { title: e2eTitle('무기한'), start: '', end: '' });
  created.push(id);
  await gotoTrip(page, id);
  await openPanel(page);

  await expect(dayTab(page, '1일차')).toHaveCount(0);
  const btn = addDayButton(page, testInfo);
  await expect(btn).toBeEnabled();
  await expect(btn).toContainText('1일차 추가');
  await btn.click();
  await expect(dayTab(page, '1일차')).toBeVisible();
  await expect(page.getByTestId('trip-layer-list')).toContainText('미정');
  await expect(addDayButton(page, testInfo)).toContainText('2일차 추가');
  await expect(addDayButton(page, testInfo)).toBeEnabled();
  await shot(page, 'TRIP-005', 'undated-day-added');
});

test('[TRIP-006] 지난 날짜 여행 — "지난 여행" 버킷에만 보이고 헤더 카운트에 반영', async ({ page }) => {
  const title = e2eTitle('지난');
  const { id } = await createTrip(page, { title, start: isoDate(-10), end: isoDate(-8), region: '안동' });
  created.push(id);

  await page.goto('/trips');
  await bucketButton(page, '예정').click();
  await expect(tripListCard(page, title)).toHaveCount(0);
  await bucketButton(page, '지난 여행').click();
  await expect(tripListCard(page, title)).toBeVisible();
  await expect(page.getByRole('heading', { name: '여행', level: 1 })).toBeVisible();
  // dashboard summary line: "예정 N · 지난 여행 M · 초안 K" — M must be ≥ 1 now
  await expect(page.getByText(/예정 \d+ · 지난 여행 [1-9]\d* · 초안 \d+/)).toBeVisible();
  await shot(page, 'TRIP-006', 'past-bucket');
});

test('[TRIP-007] 잘못된 날짜 — 종료일 < 시작일은 저장되지 않고 필드 오류', async ({ page }) => {
  await page.goto('/trips');
  await revealCreateForm(page);
  const title = e2eTitle('역전');
  await page.getByTestId('trip-create-title').fill(title);
  await page.getByTestId('trip-create-start').fill(isoDate(10));
  await page.getByTestId('trip-create-end').fill(isoDate(8));

  const posts: string[] = [];
  page.on('request', (req) => {
    if (req.method() === 'POST' && /\/trips$/.test(new URL(req.url()).pathname)) posts.push(req.url());
  });
  await page.getByTestId('trip-create-submit').click();

  await expect(page.getByText('종료일은 시작일 이후여야 합니다.')).toBeVisible();
  await expect(page.getByText('초안 여행을 저장했습니다.')).toHaveCount(0);
  expect(posts).toHaveLength(0);
  await expect(tripListCard(page, title)).toHaveCount(0);
  await shot(page, 'TRIP-007', 'reversed-dates');
});

test('[TRIP-008] 잘못된 날짜 — 시작일만 입력하면 둘 다 입력하라는 오류', async ({ page }) => {
  await page.goto('/trips');
  await revealCreateForm(page);
  await page.getByTestId('trip-create-title').fill(e2eTitle('시작일만'));
  await page.getByTestId('trip-create-start').fill(isoDate(10));
  await page.getByTestId('trip-create-submit').click();
  await expect(
    page.getByText('시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.'),
  ).toBeVisible();
  await expect(page.getByText('초안 여행을 저장했습니다.')).toHaveCount(0);
});

test('[TRIP-009] 제목 없이 저장 — "여행 제목을 입력하세요." 오류, 포커스 복귀', async ({ page }) => {
  await page.goto('/trips');
  await revealCreateForm(page);
  await page.getByTestId('trip-create-start').fill(isoDate(3));
  await page.getByTestId('trip-create-end').fill(isoDate(4));
  await page.getByTestId('trip-create-submit').click();
  await expect(page.getByText('여행 제목을 입력하세요.')).toBeVisible();
  await expect(page.getByTestId('trip-create-title')).toBeFocused();
});

test('[TRIP-010] 장소가 있는 상태에서 기간 축소/확장 — 기간 벗어남 배지와 일자 추가 상한', async ({ page }, testInfo) => {
  const start = isoDate(30);
  const { id } = await createTrip(page, { title: e2eTitle('기간변경'), start, end: isoDate(31), region: '안동' });
  created.push(id);
  await gotoTrip(page, id);

  // heritage family on day 2
  const name = await searchAndAddPlace(page, 2, '안동하회마을', preferFeature);
  await selectDay(page, '2일차');
  await expect(poiRows(page)).toHaveCount(1);
  await expect(poiRows(page).first()).toContainText(name);

  // shrink to a single day → day 2 is now out of range, nothing is deleted
  await openTripEdit(page);
  await page.locator('#trip-edit-end').fill(start);
  await saveTripEdit(page);
  await expect(dayTab(page, '2일차')).toBeVisible();
  await expect(page.getByTestId('trip-day-out-of-range').first()).toContainText('기간 벗어남');
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(2, 1));
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(addDayReasonHost(page, testInfo)).toContainText('여행 기간은 최대 1일입니다.');
  await shot(page, 'TRIP-010', 'shrunk');

  // extend again → badge disappears, place still there
  await openTripEdit(page);
  await page.locator('#trip-edit-end').fill(isoDate(32));
  await saveTripEdit(page);
  await expect(page.getByTestId('trip-day-out-of-range')).toHaveCount(0);
  await expect(addDayButton(page, testInfo)).toBeEnabled();
  await expect(addDayButton(page, testInfo)).toContainText('3일차 추가');
  await selectDay(page, '2일차');
  await expect(poiRows(page)).toHaveCount(1);
  await shot(page, 'TRIP-010', 'extended');
});

test('[TRIP-011] 편집 다이얼로그에서 종료일 < 시작일 — 서버는 수용, 화면은 기간 수정 안내로 일자 추가 차단', async ({ page }, testInfo) => {
  // Documented behaviour: TripUpdate (apps/api/app/schemas/trip.py) has no date-range validator,
  // unlike TripCreate. The UI then shows the add-day reason from addDayValidation().
  const { id } = await createTrip(page, { title: e2eTitle('편집역전'), start: isoDate(40), end: isoDate(41) });
  created.push(id);
  await gotoTrip(page, id);

  await openTripEdit(page);
  await page.locator('#trip-edit-start').fill(isoDate(45));
  await page.locator('#trip-edit-end').fill(isoDate(41));
  await saveTripEdit(page);

  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(addDayReasonHost(page, testInfo)).toContainText(
    '종료일이 시작일보다 빠릅니다. 여행 기간을 먼저 수정해주세요.',
  );
  if (!isMobile(testInfo)) {
    await expect(page.getByTestId('trip-top-panel')).toContainText(`${koDate(isoDate(45))} - ${koDate(isoDate(41))}`);
  }
  await shot(page, 'TRIP-011', 'edit-reversed');
});
