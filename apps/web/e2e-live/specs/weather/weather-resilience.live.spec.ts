/**
 * WX — latency budget, staleness, degraded modes, alerts (WX-020, WX-021, WX-022, WX-025).
 * Facts (PinVi main 620b6046):
 *  - trip_view_builder.py: weather batch budget 10 s per view; #622 card budget 4 s (direct) / 5 s (Map), read no-retry.
 *  - weather_card.py / trip_weather_batch.py: is_stale is always False in the public projection (Map freshness.stale is not exposed).
 *  - weather_map_state.py: section status not_loaded/unavailable → location "failed" → found if any values else unavailable.
 *  - fetch_alerts(): 특보 always from kor-travel-weather /markers alerts → metrics with forecast_style "advisory".
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot, waitForRequest } from '../../helpers/live';
import {
  D,
  TEXT,
  TRIP_VIEW_BUDGET_MS,
  annotate,
  dayOf,
  daySection,
  expectWeatherConsistent,
  onMobile,
  openDay,
  pageErrorGuard,
  poiRow,
  poiSection,
  reloadTripView,
  tripViewPattern,
  useTripCleanup,
  wxTitle,
} from '../../helpers/weather';

test.describe('weather · resilience', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용');
  const trips = useTripCleanup();

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('WX-020 4일·4장소 여행 상세 로드 < 6초 (soft)', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-020'), start: D(0), end: D(3) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const places: [number, string, string][] = [
      [1, '고씨굴', '고씨'],
      [2, '소수서원', '소수서원'],
      [3, '도산서원', '도산서원'],
      [4, '안동하회마을', '하회'],
    ];
    for (const [day, q, pick] of places) await searchAndAddPlace(page, day, q, (t) => t.includes(pick));

    // Cold navigation from another page so the measurement includes the view request with weather.
    await page.goto('/');
    const t0 = Date.now();
    const pending = waitForRequest(page, tripViewPattern(id));
    await page.goto(`/trips/${id}`);
    const res = await pending;
    const tView = Date.now() - t0;
    expect(res.status()).toBe(200);
    const article = await openDay(page, 1);
    await expect(daySection(article)).toBeVisible();
    const tUi = Date.now() - t0;
    annotate(`GET /trips/{id} ${tView} ms · 1일차 날씨 표시 ${tUi} ms (budget ${TRIP_VIEW_BUDGET_MS} ms)`);
    test.info().attach('WX-020-timing.json', { body: JSON.stringify({ tView, tUi, budget: TRIP_VIEW_BUDGET_MS }), contentType: 'application/json' });
    expect.soft(tView, 'trip view 응답 시간').toBeLessThan(TRIP_VIEW_BUDGET_MS);
    expect.soft(tUi, '날씨 섹션 표시까지').toBeLessThan(TRIP_VIEW_BUDGET_MS);
    await shot(page, 'WX-020', 'loaded');
  });

  test('WX-021 신선도: is_stale boolean, found 는 unavailable 문구가 아님, latest_at 나이 기록', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-021'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(res?.state).toBe('found');
    const card = day1.weather_cards[(res as { card_key: string }).card_key]!;
    expect(typeof card.is_stale).toBe('boolean');
    expect(card.latest_at, 'found 카드는 latest_at 이 있어야 한다').toBeTruthy();
    const ageH = (Date.now() - new Date(card.latest_at!).getTime()) / 3_600_000;
    annotate(`is_stale=${card.is_stale} latest_at=${card.latest_at} age=${ageH.toFixed(1)}h styles=${card.source_styles.join(',')}`);
    expect.soft(ageH, '최신 known_at 이 48시간 이내').toBeLessThan(48);
    const article = await openDay(page, 1);
    const section = daySection(article);
    await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    await expect(section).not.toContainText(TEXT.unavailable);
    await shot(page, 'WX-021', 'freshness');
  });

  test('WX-022 강등 관찰: unavailable 은 문구로만, 페이지는 멀쩡', async ({ page }) => {
    const errors = pageErrorGuard(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-022'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const n1 = await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    const n2 = await searchAndAddPlace(page, 2, '성산일출봉', (t) => t.includes('성산일출봉'));
    const view = await reloadTripView(page, id);
    const counts: Record<string, number> = {};
    for (const [dayIndex, name] of [[1, n1], [2, n2]] as const) {
      const day = dayOf(view, dayIndex);
      const article = await openDay(page, dayIndex);
      for (const poi of day.pois) {
        if (!poi.feature_id) continue;
        const r = day.weather_by_feature_id[poi.feature_id];
        counts[r?.state ?? 'none'] = (counts[r?.state ?? 'none'] ?? 0) + 1;
        await expectWeatherConsistent(poiSection(poiRow(article, name)), r, day.weather_cards, day.effective_date!);
      }
    }
    annotate(`states=${JSON.stringify(counts)}`);
    await expect(page.getByTestId('trip-detail-error')).toHaveCount(0);
    expect(errors(), 'pageerror 없음').toEqual([]);
    expect.soft(counts.unavailable ?? 0, 'unavailable 이 있으면 Map/weather 강등 — 조사 필요').toBe(0);
    await shot(page, 'WX-022', 'degraded-observe');
  });

  test('WX-025 특보(advisory) 조건부 표시', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-025'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const n1 = await searchAndAddPlace(page, 1, '서울역', (t) => t.includes('서울역'));
    const n2 = await searchAndAddPlace(page, 1, '성산일출봉', (t) => t.includes('성산일출봉'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const article = await openDay(page, 1);
    let advisories = 0;
    for (const [poi, name] of [[day1.pois[0], n1], [day1.pois[1], n2]] as const) {
      const r = day1.weather_by_feature_id[poi!.feature_id!];
      if (r?.state !== 'found') continue;
      const card = day1.weather_cards[(r as { card_key: string }).card_key]!;
      const adv = card.metrics.filter((m) => m.forecast_style === 'advisory');
      advisories += adv.length;
      if (adv.length === 0) continue;
      const text = await poiSection(poiRow(article, name)).innerText();
      const hit = adv.some((m) => (m.severity && text.includes(m.severity)) || (m.metric_name && text.includes(m.metric_name)) || text.includes(m.metric_key));
      annotate(`${name} advisory=${adv.map((m) => `${m.metric_key}/${m.severity ?? ''}`).join(',')} shown=${hit}`);
      expect.soft(hit, `${name} 특보가 장소 날씨에 보여야 한다`).toBeTruthy();
    }
    if (advisories === 0) annotate('현재 특보 없음 — 표시 단언 생략(통과)');
    await shot(page, 'WX-025', 'advisory');
  });
});
