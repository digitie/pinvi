import { expect, test, type BrowserContext, type Page } from '@playwright/test';

const liveEnabled =
  process.env.PINVI_LIVE_ATTACHMENT_E2E === '1' || process.env.PINVI_LIVE_MUTATING_E2E === '1';
const webBaseUrl =
  process.env.PINVI_LIVE_WEB_URL ??
  process.env.PINVI_ADMIN_LIVE_WEB_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://127.0.0.1:12805';
const initialApiBaseUrl = process.env.PINVI_LIVE_API_URL ?? null;
const liveEmail = process.env.PINVI_LIVE_EMAIL ?? process.env.PINVI_ADMIN_LIVE_EMAIL;
const livePassword = process.env.PINVI_LIVE_PASSWORD ?? process.env.PINVI_ADMIN_LIVE_PASSWORD;
const testPrefix = process.env.PINVI_LIVE_TRIP_PREFIX ?? '[codex-live-upload]';

function assertLiveEnv() {
  const missing = [
    ['PINVI_LIVE_WEB_URL 또는 PINVI_ADMIN_LIVE_WEB_URL', webBaseUrl],
    ['PINVI_LIVE_EMAIL 또는 PINVI_ADMIN_LIVE_EMAIL', liveEmail],
    ['PINVI_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_PASSWORD', livePassword],
  ].filter(([, value]) => !value);
  if (missing.length > 0) {
    throw new Error(`${missing.map(([name]) => name).join(', ')} 환경변수가 필요합니다.`);
  }
}

function recordApiOrigin(page: Page, setApiOrigin: (origin: string) => void) {
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      url.pathname === '/auth/login' ||
      url.pathname === '/auth/me' ||
      url.pathname === '/trips' ||
      url.pathname.startsWith('/trips/')
    ) {
      setApiOrigin(url.origin);
    }
  });
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByTestId('login-email').fill(liveEmail!);
  await page.getByTestId('login-password').fill(livePassword!);
  await page.getByTestId('login-submit').click();
  await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/);
}

async function createTrip(page: Page, title: string) {
  await page.getByRole('button', { name: '관리 열기' }).click();
  await page.getByTestId('trip-create-title').fill(title);
  await page.getByTestId('trip-create-region').fill('라이브 검증');
  await page.getByTestId('trip-create-start').fill('2026-07-10');
  await page.getByTestId('trip-create-end').fill('2026-07-11');
  await page.getByTestId('trip-create-submit').click();
  await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();

  const link = page.getByTestId('trip-list').getByRole('link').filter({ hasText: title }).first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute('href');
  const match = href?.match(/\/trips\/([0-9a-f-]{36})/i);
  if (!match) throw new Error(`생성된 여행 링크에서 trip_id를 찾지 못했습니다: ${href ?? 'null'}`);
  return { tripId: match[1]!, href: href! };
}

async function cleanupTrip(context: BrowserContext, apiOrigin: string | null, tripId: string) {
  if (!apiOrigin) return;
  const res = await context.request.delete(new URL(`/trips/${tripId}`, apiOrigin).toString(), {
    data: { mode: 'soft_delete' },
  });
  if (!res.ok() && res.status() !== 404) {
    console.warn(`live trip cleanup failed: HTTP ${res.status()} ${await res.text()}`);
  }
}

test.describe('Trip upload and mobile map layout live mutating smoke', () => {
  test.skip(!liveEnabled, 'PINVI_LIVE_ATTACHMENT_E2E=1 일 때만 첨부 live e2e를 실행합니다.');

  test.use({
    viewport: { width: 412, height: 915 },
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36',
  });

  test('모바일 지도 우선 레이아웃에서 첨부 업로드와 API proxy 다운로드 URL이 동작한다', async ({
    page,
    context,
  }) => {
    assertLiveEnv();

    let apiOrigin = initialApiBaseUrl ? new URL(initialApiBaseUrl).origin : null;
    const uploadUrls: string[] = [];
    const title = `${testPrefix} ${Date.now()}`;
    const filename = `pinvi-live-samsung-${Date.now()}.jpg`;
    let tripId: string | null = null;

    recordApiOrigin(page, (origin) => {
      apiOrigin = origin;
    });
    page.on('request', (request) => {
      if (request.method() === 'PUT' && request.url().includes('/storage/uploads/')) {
        uploadUrls.push(request.url());
      }
    });
    await page.addInitScript(() => {
      Object.defineProperty(window, 'open', {
        value: (url: string | URL | undefined) => {
          (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl = String(url);
          return null;
        },
      });
    });

    try {
      await login(page);
      const created = await createTrip(page, title);
      tripId = created.tripId;

      await page.goto(created.href);
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expect(page.getByTestId('trip-detail-panel')).toBeHidden();

      const map = page.getByTestId('trip-detail-map');
      await expect(map).toBeVisible();
      const mapBox = await map.boundingBox();
      expect(mapBox?.width ?? 0).toBeGreaterThan(360);
      expect(mapBox?.height ?? 0).toBeGreaterThan(520);
      await expect(
        page.getByTestId('vworld-map-fallback').or(page.locator('.maplibregl-canvas').first()),
      ).toBeVisible({
        timeout: 20_000,
      });

      await page.getByRole('button', { name: '패널 열기' }).click();
      await expect(page.getByTestId('trip-detail-panel')).toBeVisible();
      await page.getByRole('tab', { name: '파일' }).click();
      await expect(page.getByRole('heading', { name: '첨부', exact: true })).toBeVisible();

      const attachmentInput = page.getByTestId('attachment-input').last();
      await attachmentInput.setInputFiles({
        name: 'blocked.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('not allowed'),
      });
      const mimeAlert = page.getByRole('alert').filter({ hasText: '업로드 가능한 파일 형식' });
      await expect(mimeAlert).toBeVisible();
      await expect(mimeAlert).not.toContainText('[');

      await attachmentInput.setInputFiles({
        name: filename,
        mimeType: '',
        buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
      });
      const uploadedItem = page
        .getByTestId('trip-attachment-list')
        .getByRole('listitem')
        .filter({ hasText: filename });
      await expect(uploadedItem).toBeVisible({ timeout: 30_000 });
      expect(uploadUrls.some((url) => url.includes('/storage/uploads/'))).toBe(true);
      expect(uploadUrls.join('\n')).not.toContain('127.0.0.1');
      expect(uploadUrls.join('\n')).not.toContain('localhost');

      await uploadedItem.getByRole('button', { name: '다운로드' }).click();
      await expect
        .poll(() =>
          page.evaluate(
            () => (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl ?? '',
          ),
        )
        .not.toBe('');
      const openedUrl = await page.evaluate(
        () => (window as Window & { __pinviOpenedUrl?: string }).__pinviOpenedUrl ?? '',
      );
      expect(openedUrl).toContain('/storage/downloads/');
      expect(openedUrl).not.toContain('127.0.0.1');
      expect(openedUrl).not.toContain('localhost');

      await uploadedItem.getByRole('button', { name: '삭제' }).click();
      await expect(uploadedItem).toHaveCount(0);
    } finally {
      if (tripId) {
        await cleanupTrip(context, apiOrigin, tripId);
      }
    }
  });
});
