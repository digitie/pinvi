/**
 * POI area — attachments per trip / day / place, limits, download, token hygiene, mobile.
 * Cases: POI-020, 021, 022, 023, 024, 025, 026(mobile), 028.
 * Files are named `[e2e]-…` so the /files sweep (POI-027) can catch leftovers. Every test deletes
 * its own rows first; POI-scope rows are also swept because they survive trip deletion.
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
  lastOpenedUrl,
  openFilesTab,
  openPanelIfMobile,
  PDF_BYTES,
  PNG_BYTES,
  poiRow,
  selectDay,
  snap,
  stubWindowOpen,
  sweepE2eFiles,
  uploadTo,
} from '../../helpers/poi';

let tripId: string | null = null;
let tripTitle = '';

async function freshTrip(page: Page, label: string): Promise<string> {
  await loginAsUser(page);
  tripTitle = e2eName(label);
  const trip = await createTrip(page, { title: tripTitle, start: '2026-11-05', end: '2026-11-05' });
  tripId = trip.id;
  await gotoTrip(page, trip.id);
  return trip.id;
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
    // fall through
  }
  await deleteTrip(page, id);
  // POI-scope attachments have trip_id=NULL and stay listed for the uploader after the trip is gone.
  await sweepE2eFiles(page);
});

test.describe('attachments (desktop)', () => {
  test.skip(({ isMobile }) => isMobile, 'desktop-only cases');

  test('POI-020 여행 첨부 — 이미지 업로드·목록·다운로드·삭제', async ({ page }) => {
    await stubWindowOpen(page);
    const id = await freshTrip(page, 'POI 파일여행');
    const putUrls: string[] = [];
    page.on('request', (r) => {
      if (r.method() === 'PUT' && r.url().includes('/storage/uploads/')) putUrls.push(r.url());
    });
    const section = await openFilesTab(page);
    const name = e2eFileName('trip', 'jpg');
    const created = page.waitForResponse(
      (r) => r.request().method() === 'POST' && new URL(r.url()).pathname === `/trips/${id}/attachments`,
    );
    const row = await uploadTo(section, { name, mimeType: 'image/jpeg', buffer: JPEG_BYTES });
    expect((await created).status()).toBe(201);
    expect(putUrls.length).toBe(1);
    expect(putUrls[0]).not.toMatch(/127\.0\.0\.1|localhost/);
    await expect(row).toContainText('image/jpeg · 4 B');
    await snap(page, 'POI-020', 'uploaded');

    await row.getByRole('button', { name: '다운로드' }).click();
    const opened = await lastOpenedUrl(page);
    expect(opened).toContain('/storage/downloads/');
    expect(opened).not.toMatch(/127\.0\.0\.1|localhost/);

    await deleteAttachmentRow(row);
    await expect(section.getByText('파일 없음')).toBeVisible();
  });

  test('POI-021 일자 첨부 — PDF 업로드 후 /files 에 "날짜" 범위', async ({ page }) => {
    await freshTrip(page, 'POI 파일일자');
    await selectDay(page, 1);
    const section = attachmentSection(page, '1일차 파일');
    const name = e2eFileName('day', 'pdf');
    const row = await uploadTo(section, { name, mimeType: 'application/pdf', buffer: PDF_BYTES });
    await expect(row).toContainText('application/pdf');
    await snap(page, 'POI-021', 'day-uploaded');

    await page.goto('/files');
    const fileRow = page.getByTestId('my-file-list').getByRole('listitem').filter({ hasText: name });
    await expect(fileRow).toHaveCount(1);
    await expect(fileRow).toContainText('날짜');
    await expect(fileRow).toContainText(tripTitle);
    await fileRow.getByRole('button', { name: '삭제' }).click();
    const dialog = page.getByTestId('file-delete-confirm');
    await expect(dialog).toContainText(name);
    await dialog.getByRole('button', { name: '삭제' }).click();
    await expect(fileRow).toHaveCount(0);
  });

  test('POI-022 장소(my-POI) 첨부 — 인라인 업로드, /files 에 "장소" 범위', async ({ page }) => {
    const id = await freshTrip(page, 'POI 파일장소');
    await selectDay(page, 1);
    const poiName = e2eName('파일장소');
    await createManualPoi(page, id, poiName);
    const section = poiRow(page, poiName).locator('section[aria-label="첨부"]').filter({
      has: page.getByRole('heading', { name: '장소 파일' }),
    });
    const name = e2eFileName('poi', 'png');
    const created = page.waitForResponse(
      (r) => r.request().method() === 'POST' && /\/trips\/[0-9a-f-]{36}\/pois\/[0-9a-f-]{36}\/attachments$/.test(new URL(r.url()).pathname),
    );
    await uploadTo(section, { name, mimeType: 'image/png', buffer: PNG_BYTES });
    expect((await created).status()).toBe(201);
    await snap(page, 'POI-022', 'poi-uploaded');

    await page.goto('/files');
    const fileRow = page.getByTestId('my-file-list').getByRole('listitem').filter({ hasText: name });
    await expect(fileRow).toHaveCount(1);
    await expect(fileRow).toContainText('장소');
    await expect(fileRow).toContainText(poiName); // trip_id is NULL for POI scope → poi_label shown
  });

  test('POI-023 text/plain 은 클라이언트에서 거부, 요청 없음', async ({ page }) => {
    await freshTrip(page, 'POI 파일형식');
    let presigns = 0;
    page.on('request', (r) => {
      if (new URL(r.url()).pathname === '/storage/upload-urls') presigns += 1;
    });
    const section = await openFilesTab(page);
    await section.getByTestId('attachment-input').setInputFiles({
      name: 'blocked.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not allowed'),
    });
    const alert = section.getByRole('alert');
    await expect(alert).toHaveText('업로드 가능한 파일 형식은 GIF, JPG, MP4, PDF, PNG, WEBP입니다.');
    expect(presigns).toBe(0);
    await snap(page, 'POI-023', 'mime-rejected');
  });

  test('POI-024 개별 파일 크기 한도 초과 → 422 FILE_TOO_LARGE', async ({ page }) => {
    await freshTrip(page, 'POI 파일크기');
    let puts = 0;
    page.on('request', (r) => {
      if (r.method() === 'PUT' && r.url().includes('/storage/uploads/')) puts += 1;
    });
    const section = await openFilesTab(page);
    const name = e2eFileName('big', 'jpg');
    const presign = page.waitForResponse((r) => new URL(r.url()).pathname === '/storage/upload-urls');
    await section.getByTestId('attachment-input').setInputFiles({
      name,
      mimeType: 'image/jpeg',
      buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 0xff),
    });
    const res = await presign;
    if (res.status() === 200) {
      // the account has a raised limit — remove what got uploaded and report
      const row = section.getByTestId('trip-attachment-list').getByRole('listitem').filter({ hasText: name });
      await expect(row).toBeVisible({ timeout: 90_000 });
      await deleteAttachmentRow(row);
      test.skip(true, 'attachment_max_upload_bytes 가 10 MiB 보다 크다(관리자 설정/사용자 override) — 한도 단언 불가');
    }
    expect(res.status()).toBe(422);
    const alert = section.getByRole('alert');
    await expect(alert).toContainText('최대');
    await expect(alert).toContainText('bytes');
    expect(puts).toBe(0);
    await snap(page, 'POI-024', 'too-large');
  });

  test('POI-025 업로드/다운로드 토큰이 콘솔·DOM 에 노출되지 않는다', async ({ page }) => {
    await stubWindowOpen(page);
    const consoleLines: string[] = [];
    page.on('console', (m) => consoleLines.push(m.text()));
    page.on('pageerror', (e) => consoleLines.push(String(e)));
    const id = await freshTrip(page, 'POI 토큰');
    const putTokens: string[] = [];
    page.on('request', (r) => {
      const m = r.url().match(/\/storage\/uploads\/([^/?]+)/);
      if (r.method() === 'PUT' && m) putTokens.push(m[1]!);
    });
    const section = await openFilesTab(page);
    const name = e2eFileName('token', 'jpg');
    const row = await uploadTo(section, { name, mimeType: 'image/jpeg', buffer: JPEG_BYTES });
    await row.getByRole('button', { name: '다운로드' }).click();
    const opened = await lastOpenedUrl(page);
    const downloadToken = opened.match(/\/storage\/downloads\/([^/?]+)/)?.[1] ?? '';

    expect(putTokens.length).toBe(1);
    expect(putTokens[0]!.length).toBeGreaterThan(40);
    expect(downloadToken.length).toBeGreaterThan(40);
    const joined = consoleLines.join('\n');
    expect(joined).not.toContain('/storage/uploads/');
    expect(joined).not.toContain('/storage/downloads/');
    expect(joined).not.toContain('X-Amz-');
    expect(joined).not.toContain(putTokens[0]!);
    expect(joined).not.toContain(downloadToken);
    const bodyText = await page.evaluate(() => document.body.innerText);
    expect(bodyText).not.toContain('/storage/');
    expect(bodyText).not.toContain(downloadToken);
    await snap(page, 'POI-025', 'hygiene');
    await deleteAttachmentRow(row);
    void id;
  });

  test('POI-028 첨부 목록 토글과 빈 상태', async ({ page }) => {
    await freshTrip(page, 'POI 토글');
    await selectDay(page, 1);
    const section = attachmentSection(page, '1일차 파일');
    const toggle = section.getByTestId('trip-attachment-toggle');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(toggle).toHaveAccessibleName('1일차 파일 목록 열기');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(section.getByText('파일 없음')).toBeVisible();
    await expect(toggle).toHaveAccessibleName('1일차 파일 목록 닫기');
    await toggle.click();
    await expect(section.getByText('파일 없음')).toHaveCount(0);
  });
});

test.describe('attachments (mobile)', () => {
  test.skip(({ isMobile }) => !isMobile, 'mobile project only (390x844)');

  test('POI-026 패널 열기 → 파일 탭 → 업로드·삭제', async ({ page }) => {
    await freshTrip(page, 'POI 모바일파일');
    await expect(page.getByTestId('trip-detail-panel')).toBeHidden();
    const mapBox = await page.getByTestId('trip-detail-map').boundingBox();
    expect(mapBox?.height ?? 0).toBeGreaterThan(520);
    await openPanelIfMobile(page);
    const section = await openFilesTab(page);
    const name = e2eFileName('mobile', 'jpg');
    const row = await uploadTo(section, { name, mimeType: 'image/jpeg', buffer: JPEG_BYTES });
    await snap(page, 'POI-026', 'mobile-uploaded');
    await deleteAttachmentRow(row);
    await expect(section.getByText('파일 없음')).toBeVisible();
  });
});
