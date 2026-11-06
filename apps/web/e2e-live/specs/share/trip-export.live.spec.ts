/**
 * SHR-032 — 여행 인쇄·브라우저 PDF 저장·ICS 다운로드(#641, PR690).
 *
 * UI: apps/web/components/trips/TripExportButton.tsx (data-testid trip-export-open/-dialog/-ics/-print),
 *     TripExportDocument.tsx (미리보기 = 인쇄 본문), lib/tripExport.ts (ICS), lib/tripPrintWindow.ts (about:blank 인쇄창).
 *
 * PDF 는 브라우저 인쇄 대상 선택이라 자동 파일이 없다. 여기서는 인쇄창이 준비 완료(`data-print-ready`)까지 가고
 * `print()` 를 부르는지, 본문·referrer 정책을 확인한다(실제 print 대화상자는 띄우지 않도록 opener 쪽에서 감싼다).
 * 공유 token 은 비밀이므로 실패 메시지에 원문이 찍히지 않게 boolean 으로만 비교한다.
 */
import { readFile } from 'node:fs/promises';
import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  e2eTitle,
  isoDate,
  loginAsUser,
  searchAndAddPlace,
  shot,
} from '../../helpers/live';
import { closePanelIfMobile, setPoiNote } from '../../helpers/trip';
import {
  createShareLink,
  gotoTrip,
  openSharedInFreshContext,
  openTripTab,
} from '../../helpers/share';

test.use({ trace: 'off' }); // 공유 token 이 URL·네트워크 로그에 남는다.

const exportButton = (page: Page): Locator =>
  page.getByTestId('trip-export-open').filter({ visible: true }).first();

/** ICS 본문의 구조 검사. 줄 단위 75 octet·CRLF·VEVENT 개수·날짜를 확인한다. */
function checkCalendar(
  content: string,
  opts: { events: number; dates: string[]; secret?: string },
): void {
  expect(content.startsWith('BEGIN:VCALENDAR\r\n'), 'ICS starts with BEGIN:VCALENDAR CRLF').toBe(
    true,
  );
  expect(content.endsWith('END:VCALENDAR\r\n'), 'ICS ends with END:VCALENDAR CRLF').toBe(true);
  const lines = content.slice(0, -2).split('\r\n');
  expect(
    lines.some((l) => l.includes('\n') || l.includes('\r')),
    'no bare LF/CR inside lines',
  ).toBe(false);
  const encoder = new TextEncoder();
  const longest = Math.max(...lines.map((l) => encoder.encode(l).length));
  expect(longest, 'folded lines are ≤ 75 octets').toBeLessThanOrEqual(75);
  expect(lines.filter((l) => l === 'BEGIN:VEVENT')).toHaveLength(opts.events);
  expect(lines.filter((l) => l === 'END:VEVENT')).toHaveLength(opts.events);
  for (const date of opts.dates) {
    expect(lines, `all-day DTSTART for ${date}`).toContain(
      `DTSTART;VALUE=DATE:${date.replace(/-/g, '')}`,
    );
  }
  // 제목의 쉼표·세미콜론은 RFC 5545 TEXT 이스케이프로 나간다(unfold 후 비교).
  const unfolded = content.replace(/\r\n /g, '');
  expect(unfolded).toMatch(/SUMMARY:[^\r\n]*\\,[^\r\n]*\\;/);
  if (opts.secret)
    expect(unfolded.includes(opts.secret), 'ICS must not contain the share token').toBe(false);
  expect(/https?:\/\//.test(unfolded), 'ICS carries no URL').toBe(false);
}

async function downloadIcs(page: Page): Promise<{ name: string; content: string }> {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('trip-export-ics').click(),
  ]);
  const path = await download.path();
  return { name: download.suggestedFilename(), content: await readFile(path, 'utf8') };
}

/** Wraps window.open so the about:blank print window's print() only records the call. */
async function stubPrint(page: Page): Promise<void> {
  await page.evaluate(() => {
    const original = window.open.bind(window);
    window.open = ((...args: Parameters<typeof window.open>) => {
      const popup = original(...args);
      if (popup)
        popup.print = () => void (popup.document.documentElement.dataset.e2ePrinted = 'true');
      return popup;
    }) as typeof window.open;
  });
}

async function checkPrintWindow(page: Page, title: string, secret?: string): Promise<void> {
  await stubPrint(page);
  const [popup] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByTestId('trip-export-print').click(),
  ]);
  try {
    await expect(popup.locator('html')).toHaveAttribute('data-print-ready', 'true', {
      timeout: 15_000,
    });
    await expect(popup.locator('html')).toHaveAttribute('data-e2e-printed', 'true');
    await expect(popup.locator('meta[name="referrer"]')).toHaveAttribute('content', 'no-referrer');
    await expect(popup.getByRole('heading', { level: 1, name: title })).toBeVisible();
    expect(popup.url()).toBe('about:blank');
    if (secret) {
      const html = await popup.content();
      expect(html.includes(secret), 'print document must not contain the share token').toBe(false);
    }
  } finally {
    await popup.close();
  }
  await expect(page.getByTestId('trip-export-dialog').getByRole('alert')).toHaveCount(0);
}

test.describe('SHR-032 여행 내보내기', () => {
  const created: string[] = [];

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test.afterEach(async ({ page }) => {
    for (const id of created.splice(0)) await deleteTrip(page, id).catch(() => undefined);
  });

  test('SHR-032 상세·비로그인 공유에서 미리보기·ICS·인쇄창, 철회 뒤 공유 내보내기 없음', async ({
    page,
    browser,
  }, info) => {
    // 쉼표·세미콜론은 ICS TEXT 이스케이프 확인용이다.
    const title = e2eTitle('SHR-032 내보내기, 일정; 확인');
    const start = isoDate(25);
    const end = isoDate(26);
    const { id } = await createTrip(page, { title, start, end, region: '서울' });
    created.push(id);
    await gotoTrip(page, id, title);
    const place = await searchAndAddPlace(page, 1, '경복궁');
    const note = `[e2e] 메모 ${Date.now()}`;
    await setPoiNote(page, 0, note);
    await closePanelIfMobile(page, info); // 모바일 내보내기 버튼은 상단 패널(compact)에 있다

    // 1) 소유자 상세 — 미리보기 본문
    await exportButton(page).click();
    const dialog = page.getByTestId('trip-export-dialog');
    await expect(dialog).toBeVisible();
    const doc = dialog.getByTestId('trip-export-document');
    await expect(doc.getByRole('heading', { level: 1, name: title })).toBeVisible();
    await expect(doc.getByRole('heading', { level: 2 })).toHaveCount(2);
    await expect(doc.getByRole('heading', { level: 2 }).nth(0)).toContainText('1일차');
    await expect(doc.getByRole('heading', { level: 2 }).nth(1)).toContainText('2일차');
    await expect(doc.getByRole('heading', { level: 3 })).toContainText([`1. ${place}`]);
    await expect(doc).toContainText(note);
    await expect(doc).toContainText('도착 미정 / 출발 미정');
    await expect(doc).toContainText('등록한 장소가 없습니다.'); // 2일차는 빈 일자
    // 1일차 장소(시각 없음) → 하루 종일 1건, 빈 2일차 → 하루 종일 1건.
    await expect(dialog.getByTestId('trip-export-calendar-summary')).toHaveText(
      '캘린더에 2개 일정이 포함됩니다.',
    );
    await shot(
      page,
      'SHR-032',
      info.project.name.includes('mobile') ? 'mobile-owner-preview' : 'owner-preview',
    );

    // 2) ICS 다운로드
    const ics = await downloadIcs(page);
    expect(ics.name.endsWith('-일정.ics'), 'ICS filename').toBe(true);
    checkCalendar(ics.content, { events: 2, dates: [start, end] });

    // 3) 인쇄 / PDF 저장 — about:blank 인쇄창, no-referrer, print() 호출
    await checkPrintWindow(page, title);
    await dialog.getByRole('button', { name: '닫기', exact: true }).click();
    await expect(dialog).toHaveCount(0);

    // 4) 비로그인 공유 화면에서도 같은 내보내기, token 은 파일·인쇄 본문에 없다
    await openTripTab(page, '공유');
    const link = await createShareLink(page, { visibility: 'view_only' });
    const fresh = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(fresh.apiStatus).toBe(200);
      await expect(fresh.page.getByRole('heading', { level: 1, name: title })).toBeVisible();
      await exportButton(fresh.page).click();
      const shared = fresh.page.getByTestId('trip-export-dialog');
      await expect(shared.getByTestId('trip-export-document')).toContainText(place);
      await expect(shared.getByTestId('trip-export-calendar-summary')).toHaveText(
        '캘린더에 2개 일정이 포함됩니다.',
      );
      const sharedIcs = await downloadIcs(fresh.page);
      checkCalendar(sharedIcs.content, { events: 2, dates: [start, end], secret: link.token });
      await checkPrintWindow(fresh.page, title, link.token);
      await shot(fresh.page, 'SHR-032', 'shared-preview');
    } finally {
      await fresh.context.close();
    }

    // 5) 철회 뒤 공유 화면에는 여행도 내보내기도 없다
    const list = page.getByTestId('share-link-list');
    await list.getByRole('button', { name: '공유 링크 철회' }).click();
    await expect(list.getByRole('listitem').first()).toContainText('철회');
    const revoked = await openSharedInFreshContext(browser, id, link.token);
    try {
      expect(revoked.apiStatus).toBe(404);
      await expect(revoked.page.getByTestId('trip-export-open')).toHaveCount(0);
    } finally {
      await revoked.context.close();
    }
  });
});
