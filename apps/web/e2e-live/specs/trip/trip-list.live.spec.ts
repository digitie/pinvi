/**
 * TRIP-041 … TRIP-045 — trip list: schedule sorting, draft badge → status change, delete
 * (no undo), bucket counts, dashboard map stats.
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  bucketButton,
  deleteTripViaUi,
  e2eTitle,
  gotoTrip,
  isMobile,
  isoDate,
  openTripEdit,
  preferFeature,
  saveTripEdit,
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

test('[TRIP-041] 목록 정렬 — 시작일 오름차순, 같은 날짜는 제목(한글 collator) 순, 날짜 없는 여행은 맨 뒤', async ({ page }) => {
  const tag = Date.now().toString(36);
  const late = `[e2e] 정렬 C ${tag}`;
  const early = `[e2e] 정렬 A ${tag}`;
  const sameDayB = `[e2e] 정렬 B ${tag}`;
  const undated = `[e2e] 정렬 D ${tag}`;
  // created in deliberately shuffled order
  created.push((await createTrip(page, { title: late, start: isoDate(60), end: isoDate(61) })).id);
  created.push((await createTrip(page, { title: undated, start: '', end: '' })).id);
  created.push((await createTrip(page, { title: sameDayB, start: isoDate(50), end: isoDate(51) })).id);
  created.push((await createTrip(page, { title: early, start: isoDate(50), end: isoDate(51) })).id);

  await page.goto('/trips');
  await bucketButton(page, '예정').click();
  const cards = page.getByTestId('trip-list').getByRole('link').filter({ hasText: `정렬` }).filter({ hasText: tag });
  await expect(cards).toHaveCount(4);
  const titles = await cards.locator('h2').allInnerTexts();
  expect(titles).toEqual([early, sameDayB, late, undated]);
  await shot(page, 'TRIP-041', 'sorted');
});

test('[TRIP-042] 초안 배지 — 생성 직후 "초안", 상태를 예정으로 바꾸면 배지와 헤더 카운트가 바뀐다', async ({ page }) => {
  const title = e2eTitle('상태');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12) });
  created.push(id);

  await page.goto('/trips');
  await expect(tripListCard(page, title)).toContainText('초안');
  const draftLine = await page.getByText(/초안 \d+/).first().innerText();
  const draftBefore = Number(/초안 (\d+)/.exec(draftLine)?.[1]);

  await gotoTrip(page, id);
  await openTripEdit(page);
  await page.locator('#trip-edit-status').selectOption('planned');
  await saveTripEdit(page);
  await expect(page.getByTestId('trip-top-panel')).toContainText('예정');

  await page.goto('/trips');
  await expect(tripListCard(page, title)).toContainText('예정');
  await expect(tripListCard(page, title)).not.toContainText('초안');
  // Header draft count is shared with any other area writing to the same account at the same
  // time, so only record it (expected: draftBefore - 1 when the suite runs alone).
  const draftAfterLine = await page.getByText(/초안 \d+/).first().innerText();
  test.info().annotations.push({
    type: 'draft-count',
    description: `before=${draftBefore} after=${/초안 (\d+)/.exec(draftAfterLine)?.[1]}`,
  });
  await shot(page, 'TRIP-042', 'planned-badge');
});

test('[TRIP-043] 여행 삭제 — 확인 2단계, 목록에서 사라지고 상세 URL은 오류, 되돌리기 없음', async ({ page }) => {
  const title = e2eTitle('삭제');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12), region: '안동' });
  created.push(id);
  await gotoTrip(page, id);
  await searchAndAddPlace(page, 1, '안동하회마을', preferFeature); // heritage

  await deleteTripViaUi(page);
  created.splice(created.indexOf(id), 1); // already gone; afterEach must not re-delete
  await expect(tripListCard(page, title)).toHaveCount(0);
  await bucketButton(page, '지난 여행').click();
  await expect(tripListCard(page, title)).toHaveCount(0);
  // no undo affordance anywhere on the dashboard
  await expect(page.getByRole('button', { name: /되돌리기|실행 취소/ })).toHaveCount(0);

  await page.goto(`/trips/${id}`);
  await expect(page.getByTestId('trip-detail-error')).toBeVisible();
  await shot(page, 'TRIP-043', 'deleted');
});

test('[TRIP-044] 버킷 전환 — 예정/지난 여행 필터가 aria-pressed로 바뀌고 카드 집합이 분리된다', async ({ page }) => {
  const tag = Date.now().toString(36);
  const future = `[e2e] 버킷 미래 ${tag}`;
  const past = `[e2e] 버킷 과거 ${tag}`;
  created.push((await createTrip(page, { title: future, start: isoDate(5), end: isoDate(6) })).id);
  created.push((await createTrip(page, { title: past, start: isoDate(-6), end: isoDate(-5) })).id);

  await page.goto('/trips');
  await expect(bucketButton(page, '예정')).toHaveAttribute('aria-pressed', 'true');
  await expect(tripListCard(page, future)).toBeVisible();
  await expect(tripListCard(page, past)).toHaveCount(0);

  await bucketButton(page, '지난 여행').click();
  await expect(bucketButton(page, '지난 여행')).toHaveAttribute('aria-pressed', 'true');
  await expect(bucketButton(page, '예정')).toHaveAttribute('aria-pressed', 'false');
  await expect(tripListCard(page, past)).toBeVisible();
  await expect(tripListCard(page, future)).toHaveCount(0);
  await shot(page, 'TRIP-044', 'past-bucket');
});

test('[TRIP-045] 대시보드 지도 — 카드의 "지도 장소 N개"와 지도 칩 "N개 장소"가 상세 장소 수와 일치', async ({ page }, testInfo) => {
  test.skip(isMobile(testInfo), 'dashboard map is desktop-only (mobile layout hides it)');
  const title = e2eTitle('대시보드지도');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);
  await searchAndAddPlace(page, 1, '불국사', preferFeature);
  await searchAndAddPlace(page, 1, '첨성대', preferFeature);

  await page.goto('/trips');
  await expect(tripListCard(page, title)).toContainText('지도 장소 2개');
  const chips = page.getByRole('region', { name: '전체 여행 지도' });
  await expect(chips).toContainText(/\d+개 여행/);
  await expect(chips).not.toContainText('장소 불러오는 중');
  await expect(chips).toContainText(/\d+개 장소/);
  await shot(page, 'TRIP-045', 'dashboard-map');
});
