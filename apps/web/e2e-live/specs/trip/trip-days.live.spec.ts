/**
 * TRIP-021 … TRIP-028 — day operations: add/delete/hide/rename/colour, date-edit validation,
 * "N일차 추가" hole-filling and limit messages.
 */
import { expect, test } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  loginAsUser,
  searchAndAddPlace,
  shot,
  waitForMapIdle,
} from '../../helpers/live';
import {
  addDay,
  addDayButton,
  addDayReasonHost,
  dayDeleteButton,
  daySettingsButton,
  dayTab,
  dayVisibilityCheckbox,
  e2eTitle,
  gotoTrip,
  isoDate,
  koDate,
  mapMarkers,
  mapStats,
  openPanel,
  poiRows,
  preferFeature,
  selectDay,
  summaryPattern,
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

test('[TRIP-021] 빈 일자 삭제 후 같은 번호로 재생성 — "1일차 추가"가 구멍을 메운다', async ({ page }, testInfo) => {
  const start = isoDate(12);
  const { id } = await createTrip(page, { title: e2eTitle('구멍'), start, end: isoDate(15) });
  created.push(id);
  await gotoTrip(page, id);
  await openPanel(page);
  await expect(addDayButton(page, testInfo)).toBeDisabled();

  await selectDay(page, '1일차');
  await dayDeleteButton(page, 1).click();
  await expect(dayTab(page, '1일차')).toHaveCount(0);
  await expect(page.getByTestId('day-delete-confirm')).toHaveCount(0); // no POIs → no confirm
  await expect(addDayButton(page, testInfo)).toBeEnabled();
  await expect(addDayButton(page, testInfo)).toContainText('1일차 추가');
  await shot(page, 'TRIP-021', 'hole');

  await addDay(page, testInfo, '1일차');
  await expect(page.getByTestId('trip-layer-list')).toContainText(koDate(start));
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(4, 0));
});

test('[TRIP-022] 장소가 있는 일자 삭제 — 확인 다이얼로그 후 일자와 POI 함께 제거', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('일자삭제'), start: isoDate(12), end: isoDate(13), region: '경주' });
  created.push(id);
  await gotoTrip(page, id);

  await searchAndAddPlace(page, 2, '불국사', preferFeature); // heritage
  await searchAndAddPlace(page, 2, '첨성대', preferFeature); // heritage
  await selectDay(page, '2일차');
  await expect(poiRows(page)).toHaveCount(2);
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(2, 2));

  await dayDeleteButton(page, 2).click();
  const confirm = page.getByTestId('day-delete-confirm');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText('2일차를 삭제할까요?');
  await expect(confirm).toContainText('POI 2곳');
  await shot(page, 'TRIP-022', 'confirm');

  await confirm.getByTestId('day-delete-confirm-cancel').click();
  await expect(confirm).toHaveCount(0);
  await expect(dayTab(page, '2일차')).toBeVisible(); // cancel keeps everything

  await dayDeleteButton(page, 2).click();
  await page.getByTestId('day-delete-confirm-confirm').click();
  await expect(dayTab(page, '2일차')).toHaveCount(0);
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(1, 0));
  await waitForMapIdle(page);
  await expect(mapMarkers(page)).toHaveCount(0);
});

test('[TRIP-023] 일자 숨기기/표시 — 지도 통계와 마커가 보이는 일자만 반영, 마지막 일자는 숨길 수 없음', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('숨김'), start: isoDate(12), end: isoDate(13), region: '안동' });
  created.push(id);
  await gotoTrip(page, id);

  await searchAndAddPlace(page, 1, '안동하회마을', preferFeature); // heritage
  await searchAndAddPlace(page, 2, '도산서원', preferFeature); // heritage
  await openPanel(page);
  await waitForMapIdle(page);
  await expect(mapStats(page)).toContainText('2일 표시');
  await expect(mapStats(page)).toContainText('장소 2곳');
  await expect(mapMarkers(page)).toHaveCount(2);

  await dayVisibilityCheckbox(page, '2일차').uncheck();
  await expect(mapStats(page)).toContainText('1일 표시');
  await expect(mapStats(page)).toContainText('장소 1곳');
  await expect(mapMarkers(page)).toHaveCount(1);
  await expect(mapMarkers(page).first()).toHaveAttribute('data-day-index', '1');
  await expect(page.getByTestId('trip-layer-list')).toContainText('숨김');
  // the only remaining visible day cannot be hidden
  await expect(dayVisibilityCheckbox(page, '1일차')).toBeDisabled();
  await shot(page, 'TRIP-023', 'hidden-day-2');

  await dayVisibilityCheckbox(page, '2일차').check();
  await expect(mapStats(page)).toContainText('2일 표시');
  await expect(mapMarkers(page)).toHaveCount(2);
  await expect(dayVisibilityCheckbox(page, '1일차')).toBeEnabled();
});

test('[TRIP-024] 일자 이름·색 변경 — 탭 이름이 바뀌고 색 선택이 저장되며 새로고침 후 유지', async ({ page }) => {
  const { id } = await createTrip(page, { title: e2eTitle('일자이름'), start: isoDate(12), end: isoDate(13) });
  created.push(id);
  await gotoTrip(page, id);
  await selectDay(page, '2일차');

  await daySettingsButton(page, 2).click();
  const dialog = page.getByTestId('trip-day-title-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('2일차 설정');
  await expect(page.getByRole('button', { name: '저장', exact: true })).toBeDisabled(); // unchanged
  await page.locator('#trip-day-title-input').fill('바다 보는 날');
  await page.getByTestId('trip-day-color-P-03').click();
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(dialog).toHaveCount(0);

  await expect(dayTab(page, '바다 보는 날')).toBeVisible();
  await expect(dayTab(page, '2일차')).toHaveCount(0);
  await expect(daySettingsButton(page, 2)).toBeVisible(); // control labels stay index-based
  await shot(page, 'TRIP-024', 'renamed');

  await gotoTrip(page, id);
  await selectDay(page, '바다 보는 날');
  await daySettingsButton(page, 2).click();
  await expect(page.locator('#trip-day-title-input')).toHaveValue('바다 보는 날');
  await expect(page.getByTestId('trip-day-color-P-03')).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: '취소', exact: true }).click();
});

test('[TRIP-025] 일자 날짜를 여행 기간 밖으로 — 모달 안 필드 오류, 저장 안 됨', async ({ page }) => {
  const start = isoDate(12);
  const { id } = await createTrip(page, { title: e2eTitle('기간밖날짜'), start, end: isoDate(13) });
  created.push(id);
  await gotoTrip(page, id);
  await selectDay(page, '1일차');

  await daySettingsButton(page, 1).click();
  await page.locator('#trip-day-date-input').fill(isoDate(20));
  await page.getByRole('button', { name: '저장', exact: true }).click();
  const dialog = page.getByTestId('trip-day-title-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('여행 기간 밖의 날짜입니다. 기간을 먼저 늘려주세요.');
  await expect(page.locator('#trip-day-date-input')).toHaveAttribute('aria-invalid', 'true');
  await shot(page, 'TRIP-025', 'out-of-range-error');
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByTestId('trip-layer-list')).toContainText(koDate(start));
});

test('[TRIP-026] 일자 날짜 중복 — "이미 N일차에서 쓰는 날짜입니다." 오류', async ({ page }) => {
  test.fail(true, '#649: duplicate day date is saved (dayUsingDate compares day.date, not effective_date)');
  const start = isoDate(12);
  const { id } = await createTrip(page, { title: e2eTitle('중복날짜'), start, end: isoDate(13) });
  created.push(id);
  await gotoTrip(page, id);
  await selectDay(page, '2일차');

  await daySettingsButton(page, 2).click();
  await page.locator('#trip-day-date-input').fill(start);
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByTestId('trip-day-title-dialog')).toContainText('이미 1일차에서 쓰는 날짜입니다.');
  await page.getByRole('button', { name: '취소', exact: true }).click();
});

test('[TRIP-027] 가운데 일자 삭제 — "2일차 추가"로 라벨이 가장 낮은 빈 번호를 가리킨다', async ({ page }, testInfo) => {
  const { id } = await createTrip(page, { title: e2eTitle('가운데삭제'), start: isoDate(12), end: isoDate(14) });
  created.push(id);
  await gotoTrip(page, id);
  await selectDay(page, '2일차');
  await dayDeleteButton(page, 2).click();
  await expect(dayTab(page, '2일차')).toHaveCount(0);
  await openPanel(page); // the mobile drawer can re-render closed after the delete
  await expect(dayTab(page, '3일차')).toBeVisible();
  await expect(addDayButton(page, testInfo)).toContainText('2일차 추가');
  await expect(addDayButton(page, testInfo)).toBeEnabled();
  await addDay(page, testInfo, '2일차');
  await expect(page.getByTestId('trip-layer-list')).toContainText(koDate(isoDate(13)));
  await expect(addDayButton(page, testInfo)).toBeDisabled();
  await expect(addDayReasonHost(page, testInfo)).toContainText('여행 기간은 최대 3일입니다.');
});

test('[TRIP-028] 날짜 없는 여행 — 일자를 1·2·3 순서로 계속 추가, 상한 안내 없음', async ({ page }, testInfo) => {
  const { id } = await createTrip(page, { title: e2eTitle('무기한일자'), start: '', end: '' });
  created.push(id);
  await gotoTrip(page, id);
  await addDay(page, testInfo, '1일차');
  await addDay(page, testInfo, '2일차');
  await addDay(page, testInfo, '3일차');
  await expect(addDayButton(page, testInfo)).toContainText('4일차 추가');
  await expect(addDayButton(page, testInfo)).toBeEnabled();
  await expect(addDayReasonHost(page, testInfo)).not.toContainText('최대');
  await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(3, 0));
});
