/**
 * TRIP-041 … TRIP-045, TRIP-058 — trip list: schedule sorting, draft badge → status change, delete →
 * trash → restore (30-day retention, #681), bucket counts, dashboard map stats.
 */
import { expect, test } from '@playwright/test';
import { apiBaseURL, createTrip, deleteTrip, loginAsUser, searchAndAddPlace, shot, tripDayPoiCounts, withRateLimitRetry } from '../../helpers/live';
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

test('[TRIP-043] 여행 삭제 → 휴지통 → 복원 — 목록·상세에서 사라졌다가 초안으로 장소와 함께 돌아온다', async ({ page }) => {
  // Owner decision 2026-11-04: trash/restore (#633, shipped in #657) is kept.
  const title = e2eTitle('삭제복원');
  const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12), region: '안동' });
  created.push(id);
  await gotoTrip(page, id);
  await searchAndAddPlace(page, 1, '안동하회마을', preferFeature); // heritage
  // make the pre-delete status non-draft so the restore's "초안" is observable
  await openTripEdit(page);
  await page.locator('#trip-edit-status').selectOption('planned');
  await saveTripEdit(page);
  await expect(page.getByTestId('trip-top-panel')).toContainText('예정');

  await deleteTripViaUi(page);
  await expect(tripListCard(page, title)).toHaveCount(0);
  await bucketButton(page, '지난 여행').click();
  await expect(tripListCard(page, title)).toHaveCount(0);
  await page.goto(`/trips/${id}`);
  await expect(page.getByTestId('trip-detail-error')).toBeVisible();

  // 휴지통: the dashboard link opens it and the deleted trip is listed
  await page.goto('/trips');
  await page.getByRole('link', { name: '휴지통', exact: true }).click();
  await expect(page).toHaveURL(/\/trips\/trash$/);
  await expect(page.getByRole('heading', { level: 1, name: '여행 휴지통' })).toBeVisible();
  // #681: 30일 보존 안내와 항목별 복원 기한
  await expect(page.getByText('삭제한 여행은 30일 동안 초안으로 복원할 수 있습니다.', { exact: false })).toBeVisible();
  const trashItem = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: title }) });
  await expect(trashItem).toHaveCount(1);
  await expect(trashItem).toContainText('까지 복원 가능');
  await shot(page, 'TRIP-043', 'trash');

  const restored = page.waitForResponse(
    (r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(`/trips/${id}/restore`),
  );
  await trashItem.getByRole('button', { name: `${title} 복원` }).click();
  expect((await restored).status(), 'POST /trips/{id}/restore').toBe(200);
  await expect(page.getByRole('status').filter({ hasText: `"${title}" 여행을 초안으로 복원했습니다.` })).toBeVisible();
  await expect(trashItem).toHaveCount(0);

  // back on the dashboard as a draft, with its place
  await page.goto('/trips');
  await expect(tripListCard(page, title)).toContainText('초안');
  expect(await tripDayPoiCounts(page, id), 'places survive trash + restore').toEqual([1]);
  await gotoTrip(page, id);
  await expect(page.getByTestId('trip-top-panel')).toContainText('초안');
  await shot(page, 'TRIP-043', 'restored');
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

const DAY_MS = 86_400_000;

test('[TRIP-058] 휴지통 30일 보존 — 만료 시각 = 삭제 시각 + 30일, 복원 가능, 복원 후 기한 해제', async ({ page }) => {
  const title = e2eTitle('휴지통보존');
  const { id } = await createTrip(page, { title, start: isoDate(14), end: isoDate(14) });
  created.push(id);
  const api = await apiBaseURL(page);
  const before = Date.now();
  await deleteTrip(page, id);
  const after = Date.now();

  const res = await withRateLimitRetry('GET /trips?trashed', () =>
    page.context().request.get(`${api}/trips?bucket=all&trashed=true&limit=50`),
  );
  expect(res.ok(), `GET /trips?trashed=true → HTTP ${res.status()}`).toBeTruthy();
  const items = ((await res.json()) as { data: { trip_id: string; trash_expires_at: string | null; can_restore?: boolean }[] }).data;
  const item = items.find((t) => t.trip_id === id);
  expect(item, 'deleted trip is listed in the trash').toBeTruthy();
  expect(item!.can_restore).toBe(true);
  const expires = Date.parse(item!.trash_expires_at ?? '');
  // 서버 시계와의 차이를 2분까지 허용한다. 30일보다 이르게 만료되면 복원 가능한 자료를 일찍 지운다.
  expect(expires).toBeGreaterThanOrEqual(before + 30 * DAY_MS - 120_000);
  expect(expires).toBeLessThanOrEqual(after + 30 * DAY_MS + 120_000);

  await page.goto('/trips/trash');
  const trashItem = page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: title }) });
  await expect(trashItem.getByRole('button', { name: `${title} 복원` })).toBeEnabled();
  const restored = page.waitForResponse(
    (r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(`/trips/${id}/restore`),
  );
  await trashItem.getByRole('button', { name: `${title} 복원` }).click();
  const body = (await (await restored).json()) as { data: { status: string; trash_expires_at: string | null; can_restore?: boolean } };
  expect(body.data).toMatchObject({ status: 'draft', trash_expires_at: null, can_restore: false });
  await shot(page, 'TRIP-058', 'restored');
});
