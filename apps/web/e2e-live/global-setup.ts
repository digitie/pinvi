/**
 * Live catalog global setup — runs once before any project.
 *
 *  1. Fails fast when the base URL or the primary credentials are missing (names only in the message).
 *  2. Login smoke as the test user.
 *  3. Sweeps every `[e2e]` trip the test user still owns (leftovers from an aborted run).
 *  4. Ensures the persistent seed trip `[e2e-seed] weather-sun` exists (WX-011/012 read it;
 *     the KASI fill needs ~20 min after creation, so a freshly created seed makes those two cases
 *     skip/tolerate on the first run — see the runbook).
 */
import { chromium, type Page } from '@playwright/test';
import {
  createTrip,
  deleteAllE2eTrips,
  deleteTrip,
  findTripByTitle,
  isoDate,
  loginAsUser,
  pickFeature,
  pickNotExternal,
  searchAndAddPlace,
  seedSunTripTitle,
  tripDayPoiCounts,
} from './helpers/live';

const REQUIRED = [
  'PLAYWRIGHT_BASE_URL',
  'PINVI_E2E_USER_EMAIL',
  'PINVI_E2E_USER_PASSWORD',
] as const;

/** One coord-bearing place per day (영월 → 제주 → 설악 → 서울 → 울릉). */
const SEED_PLACES: ReadonlyArray<{ query: string; pick: string }> = [
  { query: '영월 고씨굴', pick: '고씨' },
  { query: '성산일출봉', pick: '성산일출봉' },
  { query: '설악산', pick: '설악산' },
  { query: '서울역', pick: '서울역' },
  { query: '울릉도', pick: '울릉' },
];

function isCompleteSeed(counts: number[]): boolean {
  return counts.length === SEED_PLACES.length && counts.every((n) => n >= 1);
}

/**
 * Seed trip, transactional: an existing seed is kept only when complete (5 days, ≥1 place each);
 * an incomplete one (e.g. left by an aborted setup) is deleted and rebuilt. A failure while building
 * deletes the half-made trip again. Seed problems never abort the run — only WX-011/012 depend on it
 * and they skip with an explicit message when it is missing.
 */
async function ensureSeedTrip(page: Page): Promise<void> {
  const existing = await findTripByTitle(page, seedSunTripTitle);
  if (existing) {
    const counts = await tripDayPoiCounts(page, existing);
    if (isCompleteSeed(counts)) {
      console.log('[live-catalog] setup: seed trip present and complete');
      return;
    }
    console.log(
      `[live-catalog] setup: seed trip incomplete (pois per day: ${counts.join(',') || 'none'}) — rebuilding`,
    );
    await deleteTrip(page, existing);
  }
  let id: string | null = null;
  try {
    ({ id } = await createTrip(page, {
      title: seedSunTripTitle,
      start: isoDate(30),
      end: isoDate(34),
      region: '전국',
    }));
    await page.goto(`/trips/${id}`);
    for (let day = 1; day <= SEED_PLACES.length; day += 1) {
      const place = SEED_PLACES[day - 1]!;
      try {
        await searchAndAddPlace(
          page,
          day,
          place.query,
          // oxlint-disable-next-line react-doctor/js-set-map-lookups -- string 부분 검색이며 Set 원소 비교로 대체할 수 없다.
          (row) => row.includes(place.pick) && pickFeature(row),
        );
      } catch {
        // no Map feature row for this query → any non-Kakao/Naver row carrying the name (coords suffice)
        await searchAndAddPlace(
          page,
          day,
          place.query,
          // oxlint-disable-next-line react-doctor/js-set-map-lookups -- string 부분 검색이며 Set 원소 비교로 대체할 수 없다.
          (row) => row.includes(place.pick) && pickNotExternal(row),
        );
      }
    }
    const counts = await tripDayPoiCounts(page, id);
    if (!isCompleteSeed(counts))
      throw new Error(`seed incomplete after build: ${counts.join(',')}`);
    console.log(
      '[live-catalog] setup: seed trip created (sunrise fill needs ~20 min; WX-011/012 may skip on this run)',
    );
  } catch (err) {
    if (id) await deleteTrip(page, id).catch(() => undefined);
    console.warn(
      `[live-catalog] setup: seed trip NOT created (${(err as Error).message.split('\n')[0]}) — WX-011/012 will skip`,
    );
  }
}

export default async function globalSetup(): Promise<void> {
  const missing = REQUIRED.filter((name) => !process.env[name]);
  if (missing.length > 0) {
    throw new Error(
      `live catalog: 필수 환경변수 누락 — ${missing.join(', ')} (root-only env 파일에서 로드, 값은 출력하지 않는다)`,
    );
  }
  const baseURL = process.env.PLAYWRIGHT_BASE_URL!;
  if (/localhost|127\.0\.0\.1/.test(baseURL)) {
    throw new Error(
      'live catalog: PLAYWRIGHT_BASE_URL 은 배포된 origin 이어야 한다(#618, localhost 금지).',
    );
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const page = await context.newPage();
  try {
    await loginAsUser(page);
    const swept = await deleteAllE2eTrips(page);
    console.log(`[live-catalog] setup: login ok, swept ${swept} leftover [e2e] trip(s)`);

    await ensureSeedTrip(page);
  } finally {
    await context.close();
    await browser.close();
  }
}
