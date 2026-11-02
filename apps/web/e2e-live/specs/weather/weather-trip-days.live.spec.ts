/**
 * WX — per-day weather text in trip detail (live, prod, no mocks).
 * Cases: WX-001..009, WX-027, WX-028, WX-029.
 * Selectors/text: PinVi main 620b6046 — TripWeatherSummary.tsx, TripDetail.tsx, TripPoiList.tsx.
 */
import { expect, test } from '@playwright/test';
import { createTrip, loginAsUser, searchAndAddPlace, shot } from '../../helpers/live';
import {
  D,
  HUMIDITY_KEY_RE,
  POP_KEY_RE,
  PROVIDER_LABELS,
  TEMP_KEY_RE,
  TEMP_RANGE,
  TEMP_UNIT_RE,
  TEXT,
  WEATHER_VIA_MAP,
  annotate,
  dayOf,
  daySection,
  expectWeatherConsistent,
  loadTripView,
  onMobile,
  metricsForDate,
  numericValues,
  openDay,
  pageErrorGuard,
  poiRow,
  poiSection,
  reloadTripView,
  risePending,
  tempsInUiText,
  useTripCleanup,
  weatherKind,
  wxTitle,
  type WxResolution,
} from '../../helpers/weather';

test.describe('weather · trip days', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용(모바일은 WX-010/015)');
  const trips = useTripCleanup();

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('WX-001 오늘~모레 1일차: 현재·예보(초단기/단기) 그룹', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-001'), start: D(0), end: D(2) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const name = await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const poi = day1.pois.find((p) => p.feature_id);
    expect(poi?.feature_id, '추가된 POI 에 feature_id 가 있어야 한다').toBeTruthy();
    const res = day1.weather_by_feature_id[poi!.feature_id!];
    expect(res?.state, `오늘 날씨는 found 여야 한다 (${name})`).toBe('found');

    const article = await openDay(page, 1);
    const section = daySection(article);
    const kind = await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    expect(kind, '오늘 날짜 카드는 metric 이 있어 summary 여야 한다').toBe('summary');
    await expect(section).not.toContainText(TEXT.unavailable);
    await expect(section).toContainText(/현재|예보/);
    await expect.soft(section, '0일 차는 관측(현재)과 단기 예보가 모두 있어야 한다').toContainText(TEXT.group.current);
    await expect.soft(section).toContainText(TEXT.group.forecast);
    await shot(page, 'WX-001', 'day1-weather');

    // D+2 (short-term window) — forecast group expected.
    const day3 = dayOf(view, 3);
    if (day3.pois.length === 0) annotate('3일차에는 장소가 없어 날씨 섹션 없음(설계상 정상)');
  });

  test('WX-002 3~10일 뒤: 중기(mid) 예보 그룹', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-002'), start: D(4), end: D(6) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '소수서원', (t) => t.includes('소수서원'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const fid = day1.pois[0]?.feature_id!;
    const res = day1.weather_by_feature_id[fid];
    expect(res?.state, 'D+4 는 중기예보 범위 — found').toBe('found');

    const article = await openDay(page, 1);
    const section = daySection(article);
    const kind = await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    expect(kind).toBe('summary');
    await expect(section).toContainText(TEXT.group.forecast);
    await expect(section).not.toContainText(TEXT.group.current);
    await expect.soft(section).toContainText(/기온|최저|최고|하늘|강수/);
    const styles = new Set(metricsForDate(day1.weather_cards[(res as { card_key: string }).card_key], day1.effective_date!).map((m) => m.forecast_style));
    annotate(`D+4 forecast_styles=${[...styles].join(',')}`);
    await shot(page, 'WX-002', 'mid-forecast');
  });

  test('WX-003 10일 넘게 남은 일자: no_data 문구, unavailable 아님', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-003'), start: D(15), end: D(16) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(['found', 'no_data'], `state=${res?.state}`).toContain(res?.state);

    const article = await openDay(page, 1);
    const section = daySection(article);
    const kind = await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    expect(kind).toBe('status');
    await expect(section).toContainText(TEXT.noData);
    await expect(section).not.toContainText(TEXT.unavailable);
    await shot(page, 'WX-003', 'beyond-horizon');
  });

  test('WX-004 지난 날짜: Map 세 구간 요약(시간대별)', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-004'), start: D(-5), end: D(-4) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '도산서원', (t) => t.includes('도산서원'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(res?.state, '지난 날짜도 unavailable 은 금지').not.toBe('unavailable');

    const article = await openDay(page, 1);
    const section = daySection(article);
    const kind = await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    if (WEATHER_VIA_MAP) {
      expect(kind, 'Map 경로는 지난 일자에 daily_summaries 를 준다(§9.2)').toBe('summary');
      await expect(section).toContainText(TEXT.group.daily);
      await expect(section).toContainText(/아침|점심|저녁/);
      await expect(section).toContainText(/°C/);
    } else {
      annotate(`직접 경로(보존 2일): kind=${kind}`);
    }
    await shot(page, 'WX-004', 'past-day');
  });

  test('WX-005 같은 일자 두 지역(서울역·성산일출봉): 장소별 카드 분리, 날짜 날씨=첫 장소', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-005'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const seoul = await searchAndAddPlace(page, 1, '서울역', (t) => t.includes('서울역'));
    const jeju = await searchAndAddPlace(page, 1, '성산일출봉', (t) => t.includes('성산일출봉'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    expect(day1.pois.length).toBeGreaterThanOrEqual(2);
    const [p1, p2] = day1.pois;
    const r1 = day1.weather_by_feature_id[p1!.feature_id!];
    const r2 = day1.weather_by_feature_id[p2!.feature_id!];
    if (r1?.state === 'found' && r2?.state === 'found') {
      expect((r1 as { card_key: string }).card_key, '서울과 제주는 다른 location').not.toBe((r2 as { card_key: string }).card_key);
    } else {
      annotate(`states: ${seoul}=${r1?.state} ${jeju}=${r2?.state}`);
    }

    const article = await openDay(page, 1);
    const s1 = poiSection(poiRow(article, seoul));
    const s2 = poiSection(poiRow(article, jeju));
    await expectWeatherConsistent(s1, r1, day1.weather_cards, day1.effective_date!);
    await expectWeatherConsistent(s2, r2, day1.weather_cards, day1.effective_date!);
    const dayText = (await daySection(article).innerText()).replace(TEXT.dayLabel, '').trim();
    const firstText = (await s1.innerText()).replace(TEXT.poiLabel, '').trim();
    expect(dayText, '날짜 날씨는 첫 POI 기준').toBe(firstText);
    await shot(page, 'WX-005', 'two-regions');
  });

  test('WX-006 바다(성산일출봉): 기온·습도·강수확률 범위', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-006'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '성산일출봉', (t) => t.includes('성산일출봉'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(res?.state).toBe('found');
    const card = day1.weather_cards[(res as { card_key: string }).card_key]!;
    const temps = numericValues(card.metrics, TEMP_KEY_RE, TEMP_UNIT_RE);
    const hums = numericValues(card.metrics, HUMIDITY_KEY_RE);
    const pops = numericValues(card.metrics, POP_KEY_RE);
    annotate(`temps=${temps.length} hum=${hums.length} pop=${pops.length} latest_at=${card.latest_at}`);
    expect(temps.length, '기온 metric 이 하나는 있어야 한다').toBeGreaterThan(0);
    for (const t of temps) expect(t, 'temp °C').toBeGreaterThanOrEqual(TEMP_RANGE.min);
    for (const t of temps) expect(t, 'temp °C').toBeLessThanOrEqual(TEMP_RANGE.max);
    for (const h of hums) expect(h).toBeGreaterThanOrEqual(0);
    for (const h of hums) expect(h).toBeLessThanOrEqual(100);
    for (const p of pops) expect(p).toBeGreaterThanOrEqual(0);
    for (const p of pops) expect(p).toBeLessThanOrEqual(100);

    const article = await openDay(page, 1);
    const uiTemps = tempsInUiText(await daySection(article).innerText());
    for (const t of uiTemps) {
      expect(t).toBeGreaterThanOrEqual(TEMP_RANGE.min);
      expect(t).toBeLessThanOrEqual(TEMP_RANGE.max);
    }
    await shot(page, 'WX-006', 'sea-ranges');
  });

  test('WX-007 산악(설악산): found/no_data 만, 기온 범위', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-007'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const name = await searchAndAddPlace(page, 1, '설악산', (t) => t.includes('설악산'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(['found', 'no_data'], `${name} state=${res?.state}`).toContain(res?.state);
    const article = await openDay(page, 1);
    const section = daySection(article);
    await expectWeatherConsistent(section, res, day1.weather_cards, day1.effective_date!);
    if (res?.state === 'found') {
      const card = day1.weather_cards[(res as { card_key: string }).card_key]!;
      for (const t of numericValues(card.metrics, TEMP_KEY_RE, TEMP_UNIT_RE)) {
        expect(t).toBeGreaterThanOrEqual(TEMP_RANGE.min);
        expect(t).toBeLessThanOrEqual(TEMP_RANGE.max);
      }
      const providers = new Set(card.metrics.map((m) => m.provider).filter(Boolean));
      annotate(`설악산 providers=${[...providers].join(',')}`);
    }
    await shot(page, 'WX-007', 'mountain');
  });

  test('WX-008 섬(울릉도): found/no_data 만', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-008'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    let name: string;
    try {
      name = await searchAndAddPlace(page, 1, '울릉도', (t) => t.includes('울릉'));
    } catch (err) {
      test.skip(true, `울릉 장소 검색 실패(데이터 없음): ${String(err)}`);
      return;
    }
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(['found', 'no_data'], `${name} state=${res?.state}`).toContain(res?.state);
    const article = await openDay(page, 1);
    await expectWeatherConsistent(daySection(article), res, day1.weather_cards, day1.effective_date!);
    annotate(`울릉 state=${res?.state}`);
    await shot(page, 'WX-008', 'island');
  });

  test('WX-009 출처(provider) 라벨 표시', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-009'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    const res = day1.weather_by_feature_id[day1.pois[0]!.feature_id!];
    expect(res?.state).toBe('found');
    const article = await openDay(page, 1);
    const section = daySection(article);
    expect(await weatherKind(section)).toBe('summary');
    const sources = section.locator('span[title^="출처: "]');
    expect(await sources.count(), '그룹마다 출처 span').toBeGreaterThan(0);
    const labels = (await sources.allInnerTexts()).map((t) => t.trim());
    for (const label of labels) {
      expect(label).toMatch(/^\(.+\)$/);
      const inner = label.slice(1, -1).split(',').map((s) => s.trim());
      for (const p of inner) {
        const known = PROVIDER_LABELS.includes(p);
        if (!known) annotate(`표에 없는 provider 원문 표시: ${p}`);
      }
    }
    await shot(page, 'WX-009', 'providers');
  });

  test('WX-027 장소 전부 삭제 → 날짜 날씨 섹션 제거, 일출·일몰 pending_coord', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-027'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const name = await searchAndAddPlace(page, 1, '고씨굴', (t) => t.includes('고씨'));
    await reloadTripView(page, id);
    let article = await openDay(page, 1);
    await expect(daySection(article)).toBeVisible();

    page.once('dialog', (d) => d.accept());
    const row = poiRow(article, name);
    await row.getByRole('button', { name: '장소 삭제' }).click();
    await expect(row).toHaveCount(0);
    const view = await reloadTripView(page, id);
    const day1 = dayOf(view, 1);
    expect(day1.pois.length).toBe(0);
    article = await openDay(page, 1);
    await expect(article.getByLabel(TEXT.dayLabel)).toHaveCount(0);
    const pending = risePending(article);
    await expect(pending).toBeVisible();
    await expect(pending).toHaveAttribute('data-rise-set-status', 'pending_coord');
    await expect(pending).toHaveText(TEXT.risePending.pending_coord);
    await shot(page, 'WX-027', 'after-delete');
  });

  test('WX-028 14일 여행: 1·8일차 found, 12·14일차 no_data, unavailable 없음', async ({ page }) => {
    const { id } = await createTrip(page, { title: wxTitle('WX-028'), start: D(0), end: D(13) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    for (const dayIndex of [1, 8, 12, 14]) {
      await searchAndAddPlace(page, dayIndex, '안동하회마을', (t) => t.includes('하회'));
    }
    const view = await reloadTripView(page, id);
    const states: Record<number, string | undefined> = {};
    for (const dayIndex of [1, 8, 12, 14]) {
      const day = dayOf(view, dayIndex);
      const res: WxResolution | undefined = day.weather_by_feature_id[day.pois[0]!.feature_id!];
      states[dayIndex] = res?.state;
      expect(res?.state, `${dayIndex}일차`).not.toBe('unavailable');
      const article = await openDay(page, dayIndex);
      const kind = await expectWeatherConsistent(daySection(article), res, day.weather_cards, day.effective_date!);
      if (dayIndex === 1) expect(kind).toBe('summary');
      if (dayIndex === 8) expect.soft(kind, 'D+7 은 중기예보 범위').toBe('summary');
      if (dayIndex >= 12) {
        expect(kind).toBe('status');
        await expect(daySection(article)).toContainText(TEXT.noData);
      }
    }
    annotate(`states=${JSON.stringify(states)}`);
    await shot(page, 'WX-028', 'day14');
  });

  test('WX-029 접근성: aria-label 섹션, 아이콘 aria-hidden', async ({ page }) => {
    const errors = pageErrorGuard(page);
    const { id } = await createTrip(page, { title: wxTitle('WX-029'), start: D(0), end: D(1) });
    trips.track(id);
    await page.goto(`/trips/${id}`);
    const name = await searchAndAddPlace(page, 1, '안동하회마을', (t) => t.includes('하회'));
    const view = await loadTripView(page, id);
    const day1 = dayOf(view, 1);
    const article = await openDay(page, 1);
    const section = daySection(article);
    await expect(section).toBeVisible();
    expect(await section.evaluate((el) => el.tagName)).toBe('SECTION');
    const poiSec = poiSection(poiRow(article, name));
    await expect(poiSec).toBeVisible();
    for (const scope of [section, poiSec]) {
      const svgs = scope.locator('svg');
      const n = await svgs.count();
      for (let i = 0; i < n; i += 1) await expect(svgs.nth(i)).toHaveAttribute('aria-hidden', 'true');
    }
    const rise = article.getByTestId('trip-day-rise-set').or(article.getByTestId('trip-day-rise-set-pending'));
    await expect(rise.first()).toBeVisible();
    const riseSvgs = rise.first().locator('svg');
    for (let i = 0; i < (await riseSvgs.count()); i += 1) await expect(riseSvgs.nth(i)).toHaveAttribute('aria-hidden', 'true');
    expect(errors(), 'pageerror 없음').toEqual([]);
    annotate(`day1 states=${Object.values(day1.weather_by_feature_id).map((r) => r.state).join(',')}`);
    await shot(page, 'WX-029', 'a11y');
  });
});
