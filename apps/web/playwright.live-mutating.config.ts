import { defineConfig, devices } from '@playwright/test';

const baseURL =
  process.env.PINVI_LIVE_WEB_URL ?? process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:12805';
const testTimeoutMs = Number(process.env.PINVI_LIVE_TEST_TIMEOUT_MS ?? '120000');

export default defineConfig({
  testDir: './e2e',
  testMatch: '*-live-mutating.live.ts',
  timeout: Number.isFinite(testTimeoutMs) ? testTimeoutMs : 120_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: Number(process.env.PINVI_LIVE_WORKERS ?? '1'),
  reporter: [['list']],
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    serviceWorkers: 'block',
    // M04/M05 live failure는 root-owned fixed receipt만 남긴다. 인증·HTTP 원문이 담길 수
    // 있는 trace·screenshot·video artifact는 disposable runner 밖으로 내보내지 않는다.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    ...devices['Desktop Chrome'],
  },
});
