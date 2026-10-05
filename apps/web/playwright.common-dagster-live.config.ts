import { defineConfig, devices } from '@playwright/test';

// 고정 포트는 별도 N150 network namespace 안에서 사용한다.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'admin-common-dagster.live.ts',
  workers: 1,
  fullyParallel: false,
  timeout: 120000,
  expect: { timeout: 20000 },
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:12805', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],
});
