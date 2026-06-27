import { expect, test, type BrowserContext, type Page } from '@playwright/test';

const liveEnabled = process.env.PINVI_LIVE_MUTATING_E2E === '1';
const webBaseUrl =
  process.env.PINVI_LIVE_WEB_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://127.0.0.1:12805';
const apiBaseUrl = process.env.PINVI_LIVE_API_URL ?? 'http://127.0.0.1:12801';
const liveEmail = process.env.PINVI_LIVE_EMAIL;
const livePassword = process.env.PINVI_LIVE_PASSWORD;
const testPrefix = process.env.PINVI_LIVE_TRIP_PREFIX ?? '[codex-live-ws]';

function apiUrl(path: string) {
  return new URL(path, apiBaseUrl).toString();
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

async function createTrip(page: Page, title: string) {
  await page.goto('/trips');
  await page.getByTestId('trip-create-title').fill(title);
  await page.getByTestId('trip-create-region').fill('라이브 검증');
  await page.getByTestId('trip-create-submit').click();
  await expect(page.getByText('새 여행을 만들었습니다.')).toBeVisible();

  const link = page.getByTestId('trip-list').getByRole('link').filter({ hasText: title }).first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute('href');
  const match = href?.match(/\/trips\/([0-9a-f-]{36})/i);
  if (!match) throw new Error(`생성된 여행 링크에서 trip_id를 찾지 못했습니다: ${href ?? 'null'}`);
  return match[1]!;
}

async function installLiveWebSocketRecorder(page: Page) {
  await page.addInitScript(() => {
    const NativeWebSocket = window.WebSocket;
    const sockets: WebSocket[] = [];

    class RecordingWebSocket extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        sockets.push(this);
      }
    }

    const win = window as unknown as {
      WebSocket: typeof WebSocket;
      __pinviLiveWebSockets: WebSocket[];
    };
    win.__pinviLiveWebSockets = sockets;
    win.WebSocket = RecordingWebSocket as unknown as typeof WebSocket;
  });
}

async function liveSocketCount(page: Page) {
  return page.evaluate(() => {
    return ((window as unknown as { __pinviLiveWebSockets?: WebSocket[] }).__pinviLiveWebSockets ?? [])
      .length;
  });
}

async function waitForLiveSocket(page: Page, minCount: number) {
  await page.waitForFunction(
    (expected) => {
      const sockets =
        (window as unknown as { __pinviLiveWebSockets?: { readyState: number }[] })
          .__pinviLiveWebSockets ?? [];
      return sockets.length >= expected && sockets[sockets.length - 1]?.readyState === WebSocket.OPEN;
    },
    minCount,
  );
}

async function closeLatestLiveSocket(page: Page) {
  await page.evaluate(() => {
    const sockets = (window as unknown as { __pinviLiveWebSockets?: WebSocket[] })
      .__pinviLiveWebSockets;
    const socket = sockets?.[sockets.length - 1];
    if (!socket) throw new Error('닫을 live WebSocket이 없습니다.');
    socket.close(4000, 'live_e2e_reconnect');
  });
}

async function getTripVersion(context: BrowserContext, tripId: string) {
  const res = await context.request.get(apiUrl(`/trips/${tripId}`));
  if (!res.ok()) {
    throw new Error(`Trip 조회 실패: HTTP ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { data: { trip: { version: number } } };
  return body.data.trip.version;
}

async function updateTripTitle(context: BrowserContext, tripId: string, title: string) {
  const version = await getTripVersion(context, tripId);
  const res = await context.request.patch(apiUrl(`/trips/${tripId}`), {
    headers: { 'If-Match': String(version) },
    data: { title },
  });
  if (!res.ok()) {
    throw new Error(`Trip 수정 실패: HTTP ${res.status()} ${await res.text()}`);
  }
}

async function cleanupTrip(context: BrowserContext, tripId: string) {
  const res = await context.request.delete(apiUrl(`/trips/${tripId}`), {
    data: { mode: 'soft_delete' },
  });
  if (!res.ok() && res.status() !== 404) {
    console.warn(`live trip cleanup failed: HTTP ${res.status()} ${await res.text()}`);
  }
}

test.describe('Trip WebSocket live mutating smoke', () => {
  test.skip(!liveEnabled, 'PINVI_LIVE_MUTATING_E2E=1 일 때만 live mutating e2e를 실행합니다.');

  test('실제 WebSocket broadcast와 재연결 뒤 Trip snapshot reload가 동작한다', async ({ browser }) => {
    assertLiveEnv();

    const contextA = await browser.newContext({ baseURL: webBaseUrl, ignoreHTTPSErrors: true });
    const contextB = await browser.newContext({ baseURL: webBaseUrl, ignoreHTTPSErrors: true });
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    const title = `${testPrefix} ${Date.now()}`;
    let tripId: string | null = null;

    try {
      await installLiveWebSocketRecorder(pageB);
      await Promise.all([login(pageA), login(pageB)]);

      tripId = await createTrip(pageA, title);
      await Promise.all([pageA.goto(`/trips/${tripId}`), pageB.goto(`/trips/${tripId}`)]);
      await waitForLiveSocket(pageB, 1);
      await expect(pageB.getByTestId('trip-realtime-status')).toContainText('연결됨');
      await expect(pageB.getByTestId('trip-realtime-status')).toContainText(/접속 \d+명/);

      const firstUpdate = `${title} broadcast`;
      await updateTripTitle(contextA, tripId, firstUpdate);
      await expect(pageB.getByRole('heading', { name: firstUpdate })).toBeVisible();

      const socketCountBeforeReconnect = await liveSocketCount(pageB);
      await closeLatestLiveSocket(pageB);
      await waitForLiveSocket(pageB, socketCountBeforeReconnect + 1);
      await expect(pageB.getByTestId('trip-realtime-status')).toContainText('연결됨');

      const secondUpdate = `${title} reconnect`;
      await updateTripTitle(contextA, tripId, secondUpdate);
      await expect(pageB.getByRole('heading', { name: secondUpdate })).toBeVisible();
    } finally {
      if (tripId) {
        await cleanupTrip(contextA, tripId);
      }
      await Promise.all([contextA.close(), contextB.close()]);
    }
  });
});
