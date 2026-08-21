import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:12805';
const webPort = new URL(baseURL).port || '80';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // 모든 e2e 는 page.route 로 API 를 mock 하므로 백엔드 없이 Next 앱만 띄우면 된다.
  webServer: {
    command: `npm run build && npx next start -p ${webPort}`,
    url: baseURL,
    // NTFS worktree의 production build는 compile 뒤 static optimization까지 180초를 넘길 수 있다.
    // reuse는 금지하되, isolated server가 정상 기동할 시간을 충분히 준다.
    timeout: 600_000,
    // 다른 worktree의 12805 server를 재사용하면 route/mock 검증이 다른 artifact에 수행된다.
    reuseExistingServer: false,
  },
});
