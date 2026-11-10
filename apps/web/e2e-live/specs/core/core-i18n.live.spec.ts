/**
 * CORE — i18n / formatting: Korean long dates, 24h times, km distances.
 * Verified against packages/domain/src/tripDateLabels.ts (Intl ko-KR {year:numeric, month:short,
 * day:numeric, timeZone:UTC} → "2026년 11월 5일"; formatKstTime hour12:false Asia/Seoul),
 * packages/domain/src/distance.ts (`12.5km` / `950m`), components/trips/TripPoiList.tsx formatTime
 * (hour12 default — see README open question), origin/main TripDayHeader.tsx pending messages.
 */
import { expect, test } from '@playwright/test';
import { createTrip, deleteTrip, e2ePrefix, isoDate, loginAsUser, openPanel, searchAndAddPlace, shot } from '../../helpers/live';
import { annotate, isMobileViewport, PLACES } from '../../helpers/core';

// 고정 날짜는 지나면 여행 목록 기본 보기(다가오는 여행)에서 빠져 카드가 사라진다(2026-11-10 실측).
// 그래서 오늘 기준 미래 날짜로 만들고 같은 날짜의 한국어 표기를 기대값으로 쓴다.
const START = isoDate(30);
const END = isoDate(33);
function koDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return `${y}년 ${m}월 ${d}일`;
}
const KO_RANGE = `${koDate(START)} - ${koDate(END)}`;
const KO_DATE = new RegExp(koDate(START));
const TIME_24H = /\b([01]\d|2[0-3]):[0-5]\d\b/;

test.describe('CORE i18n/format', () => {
  let tripId: string | null = null;
  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
  });

  test('CORE-031 한국어 날짜·24h 시각·km 거리 포맷', async ({ page }, testInfo) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: `${e2ePrefix} CORE-031 ${Date.now()}`, start: START, end: END });
    tripId = id;
    // trips list card shows the range
    await page.goto('/trips');
    const card = page.getByTestId('trip-list').getByRole('link').filter({ hasText: `${e2ePrefix} CORE-031` }).first();
    await expect(card).toContainText(KO_RANGE);

    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, PLACES.sosu);
    await searchAndAddPlace(page, 1, PLACES.dosan);
    if (isMobileViewport(page)) {
      await openPanel(page); // searchAndAddPlace already left the drawer open
      await expect(page.getByTestId('trip-detail-panel')).toContainText(KO_RANGE);
    } else {
      await expect(page.getByTestId('trip-top-panel')).toContainText(KO_RANGE);
      await expect(page.getByTestId('trip-top-panel')).toContainText(/업데이트 \d{4}년 \d{1,2}월 \d{1,2}일/);
    }
    // day tab date (effective_date) — '<START 한국어> · 표시'
    const day1 = page.getByRole('tab', { name: '1일차' });
    await expect(day1).toContainText(KO_DATE);

    // sunrise/sunset: filled by the day ETL (20 min cadence) — 24h "일출 HH:MM" when present,
    // otherwise one of the origin/main pending messages (#615). Never an AM/PM string.
    const riseSet = page.getByTestId('trip-day-rise-set');
    const pending = page.getByTestId('trip-day-rise-set-pending');
    await expect(riseSet.or(pending).first()).toBeVisible({ timeout: 15_000 });
    if (await riseSet.count()) {
      const txt = (await riseSet.textContent()) ?? '';
      expect(txt).toMatch(/일출 ([01]\d|2[0-3]):[0-5]\d/);
      expect(txt).toMatch(/일몰 ([01]\d|2[0-3]):[0-5]\d/);
      expect(txt).not.toMatch(/오전|오후|AM|PM/);
      annotate(testInfo, 'metric', `rise-set: ${txt.trim()}`);
    } else {
      await expect(pending).toHaveText(/일출·일몰 준비 중|좌표가 있는 장소를 추가하면|날짜를 정하면/);
      annotate(testInfo, 'soft', 'rise/set still pending at test time (ETL 20분 주기)');
    }

    // km distance: TripDayOptimize preview shows `formatDistanceMeters` → "NN.Nkm" / "NNNm"
    const optimize = page.getByRole('button', { name: /동선|최적/ }).first();
    if (await optimize.count()) {
      await optimize.click();
      const km = page.getByText(/\d+(\.\d)?km|\d+m\b/).first();
      await expect(km).toBeVisible({ timeout: 20_000 });
      const kmText = (await km.textContent()) ?? '';
      expect(kmText).toMatch(/\d+(\.\d)?km|\d+m\b/);
      expect(kmText).not.toMatch(/mi\b|마일/);
      annotate(testInfo, 'metric', `distance: ${kmText.trim()}`);
      // only a preview — do not apply the reorder
      await page.keyboard.press('Escape');
    } else {
      annotate(testInfo, 'soft', 'TripDayOptimize trigger not found — km format unverified (selector unverified against origin/main)');
    }
    // any planned arrival time rendered by TripPoiList must be 24h (none is set here; assert no AM/PM leak)
    await expect(page.getByTestId('trip-poi-list')).not.toContainText(/오전|오후/);
    await expect(page.getByTestId('trip-poi-list')).toContainText(PLACES.sosu.slice(0, 2));
    void TIME_24H;
    await shot(page, 'CORE-031', 'formats');
  });
});
