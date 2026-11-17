import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

/**
 * Live e2e catalog (`apps/web/e2e-live`, `docs/runbooks/live-e2e-catalog.md`).
 *
 * Runs the catalogued cases against the deployed PinVi web app through a real browser. Nothing is
 * route-mocked and there is no localhost fallback (#618): `PLAYWRIGHT_BASE_URL` must be explicit —
 * `global-setup.ts` fails fast when it (or a credential) is missing, so `--list` still works
 * without env.
 *
 * Projects:
 *  - `desktop`  Chromium 1440x900
 *  - `mobile`   Chromium 390x844, `isMobile` + `hasTouch` (the mobile web layout is viewport-driven);
 *               trip scenarios (`@trs`) only when also tagged `@mobile`
 *  - `session`  TRIP-046 only (`@slow`, ~13 min). Opt in with `PINVI_E2E_SESSION=1`; the n150
 *               runner never selects it unless asked (`--project session`).
 *
 * Artifacts: trace is OFF. A Playwright trace records every action's arguments (the passwords typed by
 * the login helpers, the cookies replayed by `reuseSession`), request/response headers and DOM
 * snapshots — `sources: false` does not change that — so against production it would put credentials,
 * session tokens and share tokens into the report. Failures are diagnosed from the error, the
 * annotations and the `shot()` screenshots, which mask share URLs and Telegram chat ids.
 */
const outputRoot = process.env.PINVI_E2E_OUTPUT_DIR ?? path.resolve(__dirname, 'test-results', 'live-catalog');
const includeSession = process.env.PINVI_E2E_SESSION === '1';
/**
 * Trip scenarios (`@trs`, 190 prod trips, ~3.5 h) are opt-in: only when PINVI_E2E_TRS=1, which the n150
 * runner sets for `--area trs`. A plain full-catalog run never includes them (runbook §10).
 */
const includeTrs = process.env.PINVI_E2E_TRS === '1';
const desktopInvert = includeTrs ? [/@slow/] : [/@slow/, /@trs/];
// mobile runs only the scenarios also tagged @mobile (~10%).
const mobileInvert = includeTrs ? [/@slow/, /@trs(?!.*@mobile)/] : [/@slow/, /@trs/];

export default defineConfig({
  testDir: './e2e-live/specs',
  testMatch: '**/*.live.spec.ts',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  outputDir: path.join(outputRoot, 'artifacts'),
  globalSetup: './e2e-live/global-setup.ts',
  globalTeardown: './e2e-live/global-teardown.ts',
  reporter: [
    ['list'],
    ['html', { outputFolder: path.join(outputRoot, 'html'), open: 'never' }],
    ['json', { outputFile: path.join(outputRoot, 'results.json') }],
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL,
    ignoreHTTPSErrors: false,
    serviceWorkers: 'block',
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  projects: [
    {
      name: 'desktop',
      grepInvert: desktopInvert,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: 'mobile',
      grepInvert: mobileInvert,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
        deviceScaleFactor: 3,
      },
    },
    {
      // 2026-11-16 PC 바탕지도 누락은 Firefox·Safari에서만 났다(Chromium은 비표준 URL 스킴 전환을 허용해
      // 가렸다). `@firefox` 태그 케이스만 Firefox 데스크톱으로 한 번 더 돈다 — 기본 실행에는 없고
      // `--project desktop-firefox`로 고른다.
      name: 'desktop-firefox',
      grep: /@firefox/,
      grepInvert: desktopInvert,
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1440, height: 900 },
        // Linux headless Firefox는 GPU가 없으면 WebGL 컨텍스트를 아예 만들지 못한다
        // (`FEATURE_FAILURE_WEBGL_EXHAUSTED_DRIVERS`, `webgl.force-enabled`로도 안 풀린다) — 지도 엔진이
        // 초기화되지 않아 fallback만 보인다(2026-11-17 n150 CORE-016). 같은 이미지에서 headed Firefox는
        // Xvfb + Mesa llvmpipe로 WebGL을 얻으므로 Linux에서는 headed로 띄우고, n150 runner가
        // `xvfb-run`으로 X 서버를 준다. Windows/macOS headless Firefox는 WebGL이 있어 그대로 둔다.
        headless: process.platform !== 'linux',
      },
    },
    ...(includeSession
      ? [
          {
            name: 'session',
            grep: /@slow/,
            timeout: 20 * 60_000,
            use: {
              ...devices['Desktop Chrome'],
              viewport: { width: 1440, height: 900 },
            },
          },
        ]
      : []),
  ],
});
