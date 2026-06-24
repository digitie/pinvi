import { defineConfig, devices } from '@playwright/test';

const baseURL =
  process.env.PINVI_ADMIN_LIVE_WEB_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://127.0.0.1:12805';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'admin-live-*.live.ts',
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  workers: Number(process.env.PINVI_ADMIN_LIVE_WORKERS ?? '1'),
  reporter: [['list']],
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
});
