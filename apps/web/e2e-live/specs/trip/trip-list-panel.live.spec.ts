/**
 * Trip 일정 패널의 일자·장소 행 레이아웃(2026-11-16 소유자 요청 11·12·13).
 * Cases: TRIP-070, POI-040, POI-041.
 * Every test creates its own `[e2e]` trip and removes POIs + files + trip in afterEach.
 */
import { expect, test, type Page } from '@playwright/test';
import { createTrip, deleteTrip, loginAsUser } from '../../helpers/live';
import {
  attachmentSection,
  createManualPoi,
  deleteAllPoisInDay,
  deleteAttachmentRow,
  e2eFileName,
  e2eName,
  gotoTrip,
  JPEG_BYTES,
  poiRow,
  selectDay,
  snap,
  sweepE2eFiles,
  uploadTo,
} from '../../helpers/poi';

let tripId: string | null = null;

async function freshTrip(page: Page, label: string): Promise<string> {
  await loginAsUser(page);
  const trip = await createTrip(page, { title: e2eName(label), start: '2026-11-05', end: '2026-11-06' });
  tripId = trip.id;
  await gotoTrip(page, trip.id);
  await selectDay(page, 1);
  return trip.id;
}

/** 일자 탭 버튼과 같은 줄(편집·삭제·파일 버튼이 있는 줄). */
function dayHeaderRow(page: Page, dayIndex: number) {
  return page.getByRole('tab', { name: `${dayIndex}일차`, exact: true }).locator('xpath=..');
}

test.afterEach(async ({ page }) => {
  if (!tripId) return;
  const id = tripId;
  tripId = null;
  try {
    await gotoTrip(page, id);
    await selectDay(page, 1);
    await deleteAllPoisInDay(page);
  } catch {
    // trip may already be gone; deleteTrip below is the authoritative cleanup
  }
  await deleteTrip(page, id);
  await sweepE2eFiles(page);
});

test.describe('trip list panel (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, 'desktop-only cases');

  test('TRIP-070 일자 편집·삭제 버튼은 작고 이름이 있으며, 파일 버튼이 편집 옆·목록은 날짜 아래', async ({ page }) => {
    await freshTrip(page, '일자 버튼');
    const row = dayHeaderRow(page, 1);
    const rename = row.getByTestId('trip-day-rename');
    const remove = row.getByTestId('trip-day-delete');
    const files = row.getByTestId('trip-attachment-toggle');
    await expect(rename).toHaveAccessibleName('1일차 설정');
    await expect(remove).toHaveAccessibleName('1일차 삭제');
    await expect(files).toHaveAccessibleName('1일차 파일 목록 열기');
    for (const button of [rename, remove, files]) {
      const box = await button.boundingBox();
      // 줄였지만(이전 44px) 누름 영역은 WCAG 2.5.8 최소 24px 이상.
      expect(box?.width ?? 0).toBeGreaterThanOrEqual(24);
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(24);
      expect(box?.height ?? 99).toBeLessThan(40);
    }
    // 파일 버튼은 편집 아이콘 바로 앞에 있다.
    const fileBox = (await files.boundingBox())!;
    const renameBox = (await rename.boundingBox())!;
    expect(fileBox.x).toBeLessThan(renameBox.x);
    expect(Math.abs(fileBox.y - renameBox.y)).toBeLessThan(8);

    await expect(attachmentSection(page, '1일차 파일')).toHaveCount(0);
    await files.click();
    const section = attachmentSection(page, '1일차 파일');
    await expect(section).toBeVisible();
    // 펼친 목록은 날짜 줄 바로 아래(일자 행 안)에 있다.
    const dateLine = page.getByRole('tab', { name: '1일차', exact: true });
    const sectionBox = (await section.boundingBox())!;
    const dateBox = (await dateLine.boundingBox())!;
    expect(sectionBox.y).toBeGreaterThanOrEqual(dateBox.y + dateBox.height - 2);
    await expect(section.getByText('파일 없음')).toBeVisible();
    await snap(page, 'TRIP-070', 'day-files-open');
  });

  test('POI-040 장소 편집기 — 마커 색·아이콘·도착·출발·예산은 기본 접힘, 예산은 링크 아래', async ({ page }) => {
    const id = await freshTrip(page, '편집 접힘');
    const { title } = await createManualPoi(page, id, e2eName('접힘'));
    await poiRow(page, title).getByRole('button', { name: '마커 편집' }).click();
    const editor = page.getByTestId('poi-editor');
    await expect(editor).toBeVisible();
    for (const name of ['마커 색', '아이콘', '도착·출발', '예산·실제 비용']) {
      await expect(editor.getByRole('button', { name, exact: true })).toHaveAttribute('aria-expanded', 'false');
    }
    await expect(editor.getByLabel('예산')).toHaveCount(0);
    await expect(editor.getByLabel('도착')).toHaveCount(0);
    await expect(editor.getByRole('button', { name: '노랑' })).toHaveCount(0);
    // 예산 항목은 링크 입력 아래에 있다.
    const linkBox = (await editor.getByLabel('링크').boundingBox())!;
    const budgetToggle = editor.getByRole('button', { name: '예산·실제 비용', exact: true });
    expect((await budgetToggle.boundingBox())!.y).toBeGreaterThan(linkBox.y);
    await budgetToggle.click();
    await expect(budgetToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(editor.getByLabel('예산')).toBeVisible();
    await expect(editor.getByLabel('실제 비용')).toBeVisible();
    await snap(page, 'POI-040', 'editor-budget-open');
    await editor.getByRole('button', { name: '취소' }).click();
    await expect(editor).toBeHidden();
  });

  test('POI-041 장소 파일 버튼은 마커 편집 옆, 올리면 개수가 보인다', async ({ page }) => {
    const id = await freshTrip(page, '장소 파일');
    const { title } = await createManualPoi(page, id, e2eName('파일버튼'));
    const row = poiRow(page, title);
    const toggle = row.getByRole('button', { name: '장소 파일 목록 열기' });
    const edit = row.getByRole('button', { name: '마커 편집' });
    await expect(toggle).toBeVisible();
    const toggleBox = (await toggle.boundingBox())!;
    const editBox = (await edit.boundingBox())!;
    expect(toggleBox.x).toBeLessThan(editBox.x);
    expect(Math.abs(toggleBox.y + toggleBox.height / 2 - (editBox.y + editBox.height / 2))).toBeLessThan(8);
    await expect(toggle).toHaveAttribute('data-attachment-count', '0');
    await expect(row.locator('section[aria-label="첨부"]')).toHaveCount(0);

    await toggle.click();
    const section = row.locator('section[aria-label="첨부"]');
    const fileRow = await uploadTo(section, { name: e2eFileName('poi-count', 'jpg'), mimeType: 'image/jpeg', buffer: JPEG_BYTES });
    await expect(row.getByTestId('trip-attachment-toggle')).toHaveAttribute('data-attachment-count', '1');
    await snap(page, 'POI-041', 'poi-file-count');
    await deleteAttachmentRow(fileRow);
    await expect(row.getByTestId('trip-attachment-toggle')).toHaveAttribute('data-attachment-count', '0');
  });
});
