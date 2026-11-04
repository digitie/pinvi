/**
 * WX — shared read-only view (WX-014) and mobile compact rendering (WX-015).
 * Facts (PinVi main 620b6046):
 *  - TripShareLinks.tsx: '링크 만들기' button, data-testid new-share-url with an '열기' link href `/shared/{tripId}/{token}`.
 *  - SharedTripView.tsx: header '공유된 여행 · 읽기 전용', TripDayHeader readOnly, TripPoiList showWeather.
 *  - TripDayHeader.tsx readOnly wording: pending_fetch '일출·일몰 준비 중', other pending '일출·일몰 정보 없음'.
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  D,
  TEXT,
  annotate,
  dayOf,
  daySection,
  expectWeatherConsistent,
  onDesktop,
  onMobile,
  openDay,
  openSharedDay,
  pageErrorGuard,
  poiRow,
  poiSection,
  reloadTripView,
  useTripCleanup,
  wxTitle,
} from '../../helpers/weather';

// 공유 토큰이 URL·네트워크 로그에 남으므로 공유 링크를 여는 스펙은 trace 를 기록하지 않는다(설정 정본: playwright.live-catalog.config.ts).
test.use({ trace: 'off' });

test.describe('weather · shared view', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용');
  const trips = useTripCleanup();

  test('WX-014 공유 읽기 전용: 중립 일출·일몰 문구 + 장소 날씨', async ({ page, browser }) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-014'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const name = await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];

    await page.getByRole('tab', { name: '공유' }).click();
    await page.getByRole('button', { name: '링크 만들기' }).click();
    const box = page.getByTestId('new-share-url');
    await expect(box).toBeVisible();
    const href = await box.getByRole('link', { name: '열기' }).getAttribute('href');
    expect(href, '열기 링크 href').toMatch(/^\/shared\/[0-9a-f-]{36}\/.+/i);
    await shot(page, 'WX-014', 'share-created');

    // Anonymous context: no cookies → the shared page must still render weather + neutral sunrise wording.
    const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
    const anon = await ctx.newPage();
    const errors = pageErrorGuard(anon);
    try {
      await anon.goto(href!);
      await expect(anon.getByText(TEXT.sharedHeader)).toBeVisible();
      await openSharedDay(anon, 1);
      const sec = poiSection(poiRow(anon, name));
      await expectWeatherConsistent(sec, res, day1.weather_cards, day1.effective_date!);
      const pending1 = anon.getByTestId('trip-day-rise-set-pending');
      const success1 = anon.getByTestId('trip-day-rise-set');
      if (await success1.isVisible().catch(() => false)) {
        annotate('1일차 rise_set 이미 success');
      } else {
        await expect(pending1).toBeVisible();
        await expect(pending1).toHaveAttribute('data-rise-set-status', 'pending_fetch');
        await expect(pending1).toHaveText(TEXT.risePendingReadOnly.pending_fetch);
      }
      await shot(anon, 'WX-014', 'shared-day1');

      await openSharedDay(anon, 2);
      const pending2 = anon.getByTestId('trip-day-rise-set-pending');
      await expect(pending2).toBeVisible();
      await expect(pending2).toHaveAttribute('data-rise-set-status', 'pending_coord');
      await expect(pending2).toHaveText(TEXT.risePendingReadOnly.other);
      await expect(anon.getByText(TEXT.risePending.pending_coord)).toHaveCount(0);
      await expect(anon.getByLabel(TEXT.dayLabel)).toHaveCount(0); // shared view has no day-level weather (POI-level only)
      expect(errors()).toEqual([]);
      await shot(anon, 'WX-014', 'shared-day2');
    } finally {
      await ctx.close();
    }
  });
});

test.describe('weather · mobile', () => {
  test.setTimeout(180_000);
  test.skip(onDesktop, '모바일(390x844) 전용');
  const trips = useTripCleanup();

  test('WX-015 모바일 일자 날씨 compact, 가로 스크롤 없음', async ({ page }) => {
    await loginAsUser(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-015'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    const article = await openDay(page, 1);
    const section = daySection(article);
    await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    annotate(`scrollWidth=${overflow.scrollWidth} innerWidth=${overflow.innerWidth}`);
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.innerWidth + 1);
    const box = await section.boundingBox();
    expect(box && box.x + box.width <= overflow.innerWidth + 1, '날씨 섹션이 뷰포트 안').toBeTruthy();
    await shot(page, 'WX-015', 'mobile-day1');
  });
});
