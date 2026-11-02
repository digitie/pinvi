/**
 * TRIP-047 … TRIP-051 — mobile (390x844) variants of the key flows. Mobile layout is chosen by
 * viewport (`(max-width: 1023px)`, lib/useMobileWebLayout.ts): create form behind '관리 열기',
 * detail panel behind '패널 열기', add-day in the drawer (`trip-add-day-drawer`).
 * Runs only under the mobile project; desktop skips.
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
  addDayButton,
  copyTripViaUi,
  dayDeleteButton,
  dayTab,
  deletePoi,
  deleteTripViaUi,
  detailPanel,
  e2eTitle,
  gotoTrip,
  isoDate,
  koDate,
  mapMarkers,
  openPanel,
  poiRows,
  preferFeature,
  revealCreateForm,
  selectDay,
  summaryPattern,
  tripListCard,
} from '../../helpers/trip';

const created: string[] = [];

test.describe('TRIP mobile', () => {
  test.skip(({ isMobile: mobile }) => !mobile, 'mobile project (390x844) only');

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    while (created.length > 0) {
      const id = created.pop()!;
      await deleteTrip(page, id).catch(() => undefined);
    }
  });

  test('[TRIP-047] 모바일 생성 — "관리 열기"로 폼을 열어 1박2일 저장, 카드 확인', async ({ page }) => {
    await page.goto('/trips');
    await expect(page.getByRole('region', { name: '전체 여행 지도' })).toBeHidden();
    await revealCreateForm(page);
    const title = e2eTitle('모바일생성');
    const start = isoDate(12);
    await page.getByTestId('trip-create-title').fill(title);
    await page.getByTestId('trip-create-region').fill('강릉');
    await page.getByTestId('trip-create-start').fill(start);
    await page.getByTestId('trip-create-end').fill(isoDate(13));
    await page.getByTestId('trip-create-submit').click();
    await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();
    const card = tripListCard(page, title);
    await expect(card).toBeVisible();
    const href = await card.getAttribute('href');
    const id = /\/trips\/([0-9a-f-]{36})/i.exec(href ?? '')?.[1];
    expect(id).toBeTruthy();
    created.push(id!);
    await expect(card).toContainText(koDate(start));
    await shot(page, 'TRIP-047', 'mobile-created');
  });

  test('[TRIP-048] 모바일 상세 — 패널 열기, 드로어에서 일자 추가, 장소 추가/삭제, 헤더 "N일 · M곳"', async ({ page }, testInfo) => {
    const { id } = await createTrip(page, { title: e2eTitle('모바일상세'), start: '', end: '', region: '제주' });
    created.push(id);
    await gotoTrip(page, id);

    await expect(detailPanel(page)).toBeHidden();
    await expect(page.getByTestId('trip-add-layer')).toHaveCount(0); // desktop button absent
    await openPanel(page);
    await expect(addDayButton(page, testInfo)).toContainText('1일차 추가');
    await addDayButton(page, testInfo).click();
    await expect(dayTab(page, '1일차')).toBeVisible();

    const name = await searchAndAddPlace(page, 1, '성산일출봉', preferFeature); // heritage/natural
    await selectDay(page, '1일차');
    await expect(poiRows(page)).toHaveCount(1);
    await expect(poiRows(page).first()).toContainText(name.slice(0, 4));
    await expect(page.getByTestId('trip-top-panel')).toContainText('1일 · 1곳');
    await shot(page, 'TRIP-048', 'mobile-place-added');

    // close the drawer → map shows the marker
    await detailPanel(page).getByRole('button', { name: '패널 닫기' }).click();
    await expect(detailPanel(page)).toBeHidden();
    await waitForMapIdle(page);
    await expect(mapMarkers(page)).toHaveCount(1);
    await expect(page.getByTestId('trip-map-stats')).toContainText('장소 1곳');

    await openPanel(page);
    await selectDay(page, '1일차');
    await deletePoi(page, 0);
    await expect(page.getByTestId('trip-top-panel')).toContainText('1일 · 0곳');
  });

  test('[TRIP-049] 모바일 장소 있는 일자 삭제 — 확인 다이얼로그, 삭제 후 일자 추가 재활성', async ({ page }, testInfo) => {
    const { id } = await createTrip(page, { title: e2eTitle('모바일일자삭제'), start: isoDate(12), end: isoDate(12), region: '경주' });
    created.push(id);
    await gotoTrip(page, id);
    await searchAndAddPlace(page, 1, '불국사', preferFeature);
    await selectDay(page, '1일차');
    await expect(addDayButton(page, testInfo)).toBeDisabled();
    await dayDeleteButton(page, 1).click();
    const confirm = page.getByTestId('day-delete-confirm');
    await expect(confirm).toContainText('1일차를 삭제할까요?');
    await page.getByTestId('day-delete-confirm-confirm').click();
    await expect(dayTab(page, '1일차')).toHaveCount(0);
    await expect(addDayButton(page, testInfo)).toBeEnabled();
    await expect(addDayButton(page, testInfo)).toContainText('1일차 추가');
    await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(0, 0));
    await shot(page, 'TRIP-049', 'mobile-day-deleted');
  });

  test('[TRIP-050] 모바일 복사·삭제 — 드로어 액션으로 복사본 생성 후 두 여행 모두 삭제', async ({ page }) => {
    const title = e2eTitle('모바일복사');
    const { id } = await createTrip(page, { title, start: isoDate(12), end: isoDate(12), region: '안동' });
    created.push(id);
    await gotoTrip(page, id);
    await searchAndAddPlace(page, 1, '안동하회마을', preferFeature);

    const copyId = await copyTripViaUi(page, id);
    created.push(copyId);
    await expect(page.getByRole('heading', { name: `${title} copy` }).first()).toBeVisible();
    await selectDay(page, '1일차');
    await expect(poiRows(page)).toHaveCount(1);
    await shot(page, 'TRIP-050', 'mobile-copied');

    await deleteTripViaUi(page); // deletes the copy (current page)
    created.splice(created.indexOf(copyId), 1);
    await expect(tripListCard(page, `${title} copy`)).toHaveCount(0);
    await expect(tripListCard(page, title)).toHaveCount(1);
  });

  test('[TRIP-051] 모바일 순서 변경 — 드래그 핸들은 노출되지만 터치 DnD는 수동 확인', async ({ page }) => {
    // Scripted part: the grip ('끌어서 순서 변경') exists on mobile rows; actual touch drag is manual.
    const { id } = await createTrip(page, { title: e2eTitle('모바일순서'), start: isoDate(12), end: isoDate(12), region: '경주' });
    created.push(id);
    await gotoTrip(page, id);
    await searchAndAddPlace(page, 1, '불국사', preferFeature);
    await searchAndAddPlace(page, 1, '첨성대', preferFeature);
    await selectDay(page, '1일차');
    await expect(poiRows(page)).toHaveCount(2);
    await expect(poiRows(page).first().locator('[title="끌어서 순서 변경"]')).toHaveCount(1);
    await expect(poiRows(page).first()).toHaveAttribute('draggable', 'true');
    await shot(page, 'TRIP-051', 'mobile-grip');
  });
});
