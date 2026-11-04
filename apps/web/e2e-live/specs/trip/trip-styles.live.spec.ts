/**
 * TRIP-012 … TRIP-020 — trip styles/regions with a place mix per Map category family.
 * One table row per style; each case creates its own `[e2e]` trip and deletes it.
 *
 * Place picks prefer a Map feature row ('장소' badge) so the Map category family is really
 * exercised; lodging/food/cafe usually come back as kakao/naver rows (external_ref) which is
 * also a valid prod path (ADR-054 auto feature-request).
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
  dayTab,
  e2eTitle,
  gotoTrip,
  isoDate,
  mapMarkers,
  poiRows,
  preferExternal,
  preferFeature,
  selectDay,
  summaryPattern,
} from '../../helpers/trip';

type Pick = { day: number; query: string; family: string; external?: boolean };

interface StyleCase {
  id: string;
  style: string;
  region: string;
  nights: number; // 0 = 당일
  picks: Pick[];
}

const STYLES: StyleCase[] = [
  {
    id: 'TRIP-012',
    style: '도시 서울',
    region: '서울',
    nights: 1,
    picks: [
      { day: 1, query: '경복궁', family: 'heritage' },
      { day: 1, query: '국립중앙박물관', family: 'museum' },
      { day: 2, query: '남산공원', family: 'park' },
      { day: 2, query: '서울역', family: 'transport(station)' },
    ],
  },
  {
    id: 'TRIP-013',
    style: '도시 부산',
    region: '부산',
    nights: 1,
    picks: [
      { day: 1, query: '부산역', family: 'transport(station)' },
      { day: 1, query: '해운대해수욕장', family: 'park/beach' },
      { day: 2, query: '감천문화마을', family: 'heritage/village' },
      { day: 2, query: '해운대 호텔', family: 'lodging', external: true },
    ],
  },
  {
    id: 'TRIP-014',
    style: '바다 강릉',
    region: '강릉',
    nights: 1,
    picks: [
      { day: 1, query: '경포해변', family: 'park/beach' },
      { day: 1, query: '안목해변 카페', family: 'cafe', external: true },
      { day: 2, query: '정동진', family: 'park/beach' },
      { day: 2, query: '강릉 횟집', family: 'food', external: true },
    ],
  },
  {
    id: 'TRIP-015',
    style: '바다 제주',
    region: '제주',
    nights: 2,
    picks: [
      { day: 1, query: '성산일출봉', family: 'heritage/natural' },
      { day: 2, query: '한라산', family: 'hiking trail/park' },
      { day: 3, query: '협재해수욕장', family: 'park/beach' },
    ],
  },
  {
    id: 'TRIP-016',
    style: '산 설악산',
    region: '속초',
    nights: 1,
    picks: [
      { day: 1, query: '설악산국립공원', family: 'park' },
      { day: 1, query: '신흥사', family: 'heritage' },
      { day: 2, query: '울산바위', family: 'hiking trail' },
      { day: 2, query: '속초 펜션', family: 'lodging', external: true },
    ],
  },
  {
    id: 'TRIP-017',
    style: '산 지리산',
    region: '구례',
    nights: 1,
    picks: [
      { day: 1, query: '화엄사', family: 'heritage' },
      { day: 1, query: '지리산국립공원', family: 'park' },
      { day: 2, query: '지리산 천왕봉', family: 'hiking trail' },
    ],
  },
  {
    id: 'TRIP-018',
    style: '역사 경주',
    region: '경주',
    nights: 1,
    picks: [
      { day: 1, query: '불국사', family: 'heritage' },
      { day: 1, query: '석굴암', family: 'heritage' },
      { day: 2, query: '첨성대', family: 'heritage' },
      { day: 2, query: '국립경주박물관', family: 'museum' },
    ],
  },
  {
    id: 'TRIP-019',
    style: '역사 안동',
    region: '안동',
    nights: 1,
    picks: [
      { day: 1, query: '안동하회마을', family: 'heritage' },
      { day: 1, query: '병산서원', family: 'heritage' },
      { day: 2, query: '도산서원', family: 'heritage' },
    ],
  },
  {
    id: 'TRIP-020',
    style: '섬 울릉도',
    region: '울릉군',
    nights: 2,
    picks: [
      { day: 1, query: '독도박물관', family: 'museum' },
      { day: 2, query: '나리분지', family: 'park/natural' },
      { day: 3, query: '저동항', family: 'transport(port)' },
    ],
  },
];

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

for (const sc of STYLES) {
  test(`[${sc.id}] ${sc.style} ${sc.nights === 0 ? '당일' : `${sc.nights}박${sc.nights + 1}일`} — 카테고리 믹스 적재`, async ({ page }) => {
    const start = isoDate(21);
    const end = isoDate(21 + sc.nights);
    const { id } = await createTrip(page, {
      title: e2eTitle(sc.style),
      start,
      end,
      region: sc.region,
    });
    created.push(id);
    await gotoTrip(page, id);

    const perDay = new Map<number, string[]>();
    for (const pick of sc.picks) {
      let name: string;
      try {
        name = await searchAndAddPlace(page, pick.day, pick.query, pick.external ? preferExternal : preferFeature);
      } catch (err) {
        // Kakao/Naver are queried only when Map has < 5 internal hits; when Map already answers, take
        // the best non-external row (the family is still exercised, and no feature request auto-fires).
        if (!pick.external) throw err;
        test.info().annotations.push({ type: 'data', description: `${pick.query}: no kakao/naver row — used a Map row` });
        name = await searchAndAddPlace(page, pick.day, pick.query);
      }
      expect(name, `${pick.query} (${pick.family}) must add a named place`).not.toBe('');
      perDay.set(pick.day, [...(perDay.get(pick.day) ?? []), name]);
    }

    // per-day rows: count + order of insertion
    for (const [day, names] of perDay) {
      await selectDay(page, `${day}일차`);
      await expect(poiRows(page)).toHaveCount(names.length);
      for (let i = 0; i < names.length; i += 1) {
        await expect(poiRows(page).nth(i)).toContainText(names[i]!.slice(0, 6));
      }
      await expect(dayTab(page, `${day}일차`)).toContainText(`${names.length}곳`);
    }

    // header + map parity (all days visible by default)
    const total = sc.picks.length;
    await expect(page.getByTestId('trip-top-panel')).toContainText(summaryPattern(sc.nights + 1, total));
    await waitForMapIdle(page);
    await expect(mapMarkers(page)).toHaveCount(total);
    await expect(page.getByTestId('trip-map-stats')).toContainText(`장소 ${total}곳`);
    await shot(page, sc.id, 'loaded');
  });
}
