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
import { chromium } from '@playwright/test';
import {
  createTrip,
  deleteAllE2eTrips,
  findTripByTitle,
  isoDate,
  loginAsUser,
  searchAndAddPlace,
  seedSunTripTitle,
} from './helpers/live';

const REQUIRED = ['PLAYWRIGHT_BASE_URL', 'PINVI_E2E_USER_EMAIL', 'PINVI_E2E_USER_PASSWORD'] as const;

/** One coord-bearing place per day (영월 → 제주 → 설악 → 서울 → 울릉). */
const SEED_PLACES: ReadonlyArray<{ query: string; pick: string }> = [
  { query: '영월 고씨굴', pick: '고씨' },
  { query: '성산일출봉', pick: '성산일출봉' },
  { query: '설악산', pick: '설악산' },
  { query: '서울역', pick: '서울역' },
  { query: '울릉도', pick: '울릉' },
];

export default async function globalSetup(): Promise<void> {
  const missing = REQUIRED.filter((name) => !process.env[name]);
  if (missing.length > 0) {
    throw new Error(
      `live catalog: 필수 환경변수 누락 — ${missing.join(', ')} (root-only env 파일에서 로드, 값은 출력하지 않는다)`,
    );
  }
  const baseURL = process.env.PLAYWRIGHT_BASE_URL!;
  if (/localhost|127\.0\.0\.1/.test(baseURL) && process.env.PINVI_E2E_ALLOW_LOCAL !== '1') {
    throw new Error('live catalog: PLAYWRIGHT_BASE_URL 은 배포된 origin 이어야 한다(#618). 로컬 스택은 PINVI_E2E_ALLOW_LOCAL=1 로만.');
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const page = await context.newPage();
  try {
    await loginAsUser(page);
    const swept = await deleteAllE2eTrips(page);
    console.log(`[live-catalog] setup: login ok, swept ${swept} leftover [e2e] trip(s)`);

    const seedId = await findTripByTitle(page, seedSunTripTitle);
    if (seedId) {
      console.log('[live-catalog] setup: seed trip present');
    } else {
      const { id } = await createTrip(page, {
        title: seedSunTripTitle,
        start: isoDate(30),
        end: isoDate(34),
        region: '전국',
      });
      await page.goto(`/trips/${id}`);
      for (let day = 1; day <= SEED_PLACES.length; day += 1) {
        const place = SEED_PLACES[day - 1]!;
        await searchAndAddPlace(page, day, place.query, (row) => row.includes(place.pick) && row.includes('장소'));
      }
      console.log('[live-catalog] setup: seed trip created (sunrise fill needs ~20 min; WX-011/012 may skip on this run)');
    }
  } finally {
    await context.close();
    await browser.close();
  }
}
