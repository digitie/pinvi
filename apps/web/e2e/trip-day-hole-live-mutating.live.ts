import { expect, test, type BrowserContext, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const liveEnabled = process.env.PINVI_LIVE_MUTATING_E2E === '1';
const webBaseUrl =
  process.env.PINVI_LIVE_WEB_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://127.0.0.1:12805';
const apiBaseUrl = process.env.PINVI_LIVE_API_URL ?? 'http://127.0.0.1:12801';
const liveEmail = process.env.PINVI_LIVE_EMAIL;
const livePassword = process.env.PINVI_LIVE_PASSWORD;
const testPrefix = process.env.PINVI_LIVE_TRIP_PREFIX ?? '[codex-live-day-hole]';
const screenshotDir =
  process.env.PINVI_LIVE_SCREENSHOT_DIR ??
  path.resolve(process.cwd(), '../../.codex_tmp/live-e2e/trip-day-hole');

function apiUrl(pathname: string) {
  return new URL(pathname, apiBaseUrl).toString();
}

function assertLiveEnv() {
  const missing = [
    ['PINVI_LIVE_WEB_URL', webBaseUrl],
    ['PINVI_LIVE_API_URL', apiBaseUrl],
    ['PINVI_LIVE_EMAIL', liveEmail],
    ['PINVI_LIVE_PASSWORD', livePassword],
  ].filter(([, value]) => !value);
  if (missing.length > 0) {
    throw new Error(`${missing.map(([name]) => name).join(', ')} 환경변수가 필요합니다.`);
  }
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByTestId('login-email').fill(liveEmail!);
  await page.getByTestId('login-password').fill(livePassword!);
  await page.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/);
}

async function createDatedTrip(page: Page, title: string) {
  await page.goto('/trips');
  await page.getByTestId('trip-create-title').fill(title);
  await page.getByTestId('trip-create-region').fill('라이브 검증');
  await page.getByTestId('trip-create-start').fill('2026-11-01');
  await page.getByTestId('trip-create-end').fill('2026-11-04');
  await page.getByTestId('trip-create-submit').click();
  await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();

  const link = page.getByTestId('trip-list').getByRole('link').filter({ hasText: title }).first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute('href');
  const match = href?.match(/\/trips\/([0-9a-f-]{36})/i);
  if (!match) throw new Error(`생성된 여행 링크에서 trip_id를 찾지 못했습니다: ${href ?? 'null'}`);
  return { tripId: match[1]!, href: href! };
}

async function cleanupTrip(context: BrowserContext, tripId: string) {
  const res = await context.request.delete(apiUrl(`/trips/${tripId}`), {
    data: { mode: 'soft_delete' },
  });
  if (!res.ok() && res.status() !== 404) {
    console.warn(`live trip cleanup failed: HTTP ${res.status()} ${await res.text()}`);
  }
}

async function screenshot(page: Page, name: string) {
  await fs.mkdir(screenshotDir, { recursive: true });
  await page.screenshot({ path: path.join(screenshotDir, name), fullPage: true });
}

async function expectVisibleDays(page: Page, labels: string[]) {
  for (const label of labels) {
    await expect(page.getByRole('tab', { name: label })).toBeVisible();
  }
}

test.describe('Trip day hole live mutating flow', () => {
  test.skip(!liveEnabled, 'PINVI_LIVE_MUTATING_E2E=1 일 때만 live mutating e2e를 실행합니다.');

  test('3박4일 생성, 삭제된 1일차 재생성, 일자 날짜 수정이 실제 UI에서 동작한다', async ({
    page,
    context,
  }) => {
    assertLiveEnv();

    const title = `${testPrefix} ${Date.now()}`;
    let tripId: string | null = null;

    try {
      await login(page);
      const created = await createDatedTrip(page, title);
      tripId = created.tripId;

      await page.goto(created.href);
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expectVisibleDays(page, ['1일차', '2일차', '3일차', '4일차']);
      await expect(page.getByTestId('trip-layer-list')).toContainText('2026년 11월 1일');
      await expect(page.getByTestId('trip-layer-list')).toContainText('2026년 11월 4일');
      await expect(page.getByTestId('trip-add-day-inline')).toBeDisabled();
      await screenshot(page, '01-auto-created-1-to-4-days.png');

      await page.getByRole('tab', { name: '1일차' }).click();
      await page.getByTestId('trip-day-delete').click();
      await expect(page.getByRole('tab', { name: '1일차' })).toHaveCount(0);
      await expect(page.getByTestId('trip-add-day-inline')).toBeEnabled();
      await expect(page.getByTestId('trip-add-day-inline')).toContainText('1일차 추가');
      await screenshot(page, '02-deleted-day-1-gap.png');

      await page.getByTestId('trip-add-day-inline').click();
      await expect(page.getByRole('tab', { name: '1일차' })).toBeVisible();
      await expect(page.getByTestId('trip-layer-list')).toContainText('2026년 11월 1일');
      await expect(page.getByTestId('trip-add-day-inline')).toBeDisabled();
      await screenshot(page, '03-recreated-day-1.png');

      await page.getByRole('tab', { name: '4일차' }).click();
      await page.getByTestId('trip-day-delete').click();
      await expect(page.getByRole('tab', { name: '4일차' })).toHaveCount(0);

      await page.getByRole('tab', { name: '1일차' }).click();
      await page.getByTestId('trip-day-rename').click();
      await expect(page.getByTestId('trip-day-title-dialog')).toBeVisible();
      await page.locator('#trip-day-date-input').fill('2026-11-04');
      await page.getByRole('button', { name: '저장' }).click();
      await expect(page.getByTestId('trip-day-title-dialog')).toHaveCount(0);
      await expect(page.getByRole('tab', { name: '1일차' })).toBeVisible();
      await expect(page.getByTestId('trip-layer-list')).toContainText('2026년 11월 4일');
      await screenshot(page, '04-edited-day-1-date.png');
    } finally {
      if (tripId) {
        await cleanupTrip(context, tripId);
      }
    }
  });
});
