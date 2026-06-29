import { expect, test, type Page } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const shareId = '77777777-7777-4777-8777-777777777777';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function trip() {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title: '협업 테스트 여행',
    description: null,
    region_hint: null,
    primary_region_code: null,
    primary_region_source: null,
    start_date: null,
    end_date: null,
    visibility: 'private',
    status: 'draft',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

function poi(id: string, sort: string, title: string, lon: number) {
  return {
    poi_id: id,
    feature_id: `feat-${id}`,
    sort_order: sort,
    title,
    feature: { coord: { lon, lat: 37.5 } },
    marker_color: 'P-01',
    marker_icon: 'marker',
    is_broken: false,
    user_note: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

function tripView({
  title = '협업 테스트 여행',
  version = 1,
  shareLinks = [],
}: {
  title?: string;
  version?: number;
  shareLinks?: unknown[];
} = {}) {
  return {
    trip: { ...trip(), title, version },
    days: [
      {
        day_index: 1,
        date: null,
        title: '1일차',
        pois: [
          poi('44444444-4444-4444-8444-444444444444', '0100', '장소 A', 126.9),
          poi('44444444-4444-4444-8444-444444444445', '0200', '장소 B', 127.1),
        ],
      },
    ],
    companions: [],
    share_links: shareLinks,
    broken_feature_count: 0,
  };
}

async function commonRoutes(
  page: Page,
  {
    shareLinks = [],
    getTripView = () => tripView({ shareLinks }),
    onTripGet,
  }: {
    shareLinks?: unknown[];
    getTripView?: () => unknown;
    onTripGet?: () => void;
  } = {}
) {
  await page.route(/.*\/auth\/me$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { user_id: userId } }),
    });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/comments(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/attachments$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });
  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    onTripGet?.();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: getTripView(),
      }),
    });
  });
}

async function installControllableWebSocket(page: Page) {
  await page.addInitScript(() => {
    class ControlledWebSocket extends EventTarget {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;

      readonly url: string;
      readyState = ControlledWebSocket.CONNECTING;
      sent: string[] = [];

      constructor(url: string) {
        super();
        this.url = url;
        const win = window as unknown as { __tripWsSockets: ControlledWebSocket[] };
        win.__tripWsSockets.push(this);
        window.setTimeout(() => {
          if (this.readyState !== ControlledWebSocket.CONNECTING) return;
          this.readyState = ControlledWebSocket.OPEN;
          this.dispatchEvent(new Event('open'));
        }, 0);
      }

      send(data: string) {
        this.sent.push(String(data));
      }

      close() {
        if (this.readyState === ControlledWebSocket.CLOSED) return;
        this.readyState = ControlledWebSocket.CLOSED;
        this.dispatchEvent(new CloseEvent('close', { code: 1000, reason: 'manual', wasClean: true }));
      }

      __serverMessage(event: unknown) {
        this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }));
      }

      __serverClose(code: number, reason: string) {
        if (this.readyState === ControlledWebSocket.CLOSED) return;
        this.readyState = ControlledWebSocket.CLOSED;
        this.dispatchEvent(new CloseEvent('close', { code, reason, wasClean: false }));
      }
    }

    const win = window as unknown as {
      WebSocket: typeof WebSocket;
      __tripWsSockets: ControlledWebSocket[];
    };
    win.__tripWsSockets = [];
    win.WebSocket = ControlledWebSocket as unknown as typeof WebSocket;
  });
}

async function waitForSocketCount(page: Page, count: number) {
  await page.waitForFunction(
    (expected) => {
      const sockets = (window as unknown as { __tripWsSockets?: { readyState: number }[] })
        .__tripWsSockets;
      const all = sockets ?? [];
      return all.length >= expected && all[all.length - 1]?.readyState === WebSocket.OPEN;
    },
    count,
  );
}

async function sendServerEvent(page: Page, event: unknown, socketIndex = -1) {
  await page.evaluate(
    ({ event: payload, socketIndex: index }) => {
      const sockets = (window as unknown as { __tripWsSockets: { __serverMessage(event: unknown): void }[] })
        .__tripWsSockets;
      const target = index < 0 ? sockets[sockets.length + index] : sockets[index];
      if (!target) throw new Error(`No fake WebSocket at index ${index}`);
      target.__serverMessage(payload);
    },
    { event, socketIndex },
  );
}

async function closeServerSocket(page: Page, code: number, reason: string, socketIndex = -1) {
  await page.evaluate(
    ({ code: closeCode, reason: closeReason, socketIndex: index }) => {
      const sockets = (window as unknown as {
        __tripWsSockets: { __serverClose(code: number, reason: string): void }[];
      }).__tripWsSockets;
      const target = index < 0 ? sockets[sockets.length + index] : sockets[index];
      if (!target) throw new Error(`No fake WebSocket at index ${index}`);
      target.__serverClose(closeCode, closeReason);
    },
    { code, reason, socketIndex },
  );
}

test('공유 링크를 만들면 생성된 URL이 1회 표시된다', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/share-tokens$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          share_id: shareId,
          trip_id: tripId,
          visibility: 'view_only',
          token: 'tok-abc',
          url: 'http://127.0.0.1:12805/s/tok-abc',
          expires_at: null,
          revoked_at: null,
          last_used_at: null,
          created_at: '2026-06-01T09:00:00+09:00',
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByRole('heading', { name: '공유 링크' })).toBeVisible();

  await page.getByRole('button', { name: '링크 만들기' }).click();

  const banner = page.getByTestId('new-share-url');
  await expect(banner).toBeVisible();
  // 서버 url 대신 실제 공유 뷰 라우트(/shared/{tripId}/{token})로 구성된다.
  await expect(banner).toContainText(`/shared/${tripId}/tok-abc`);
  await expect(banner.getByRole('link', { name: '열기' })).toHaveAttribute(
    'href',
    `/shared/${tripId}/tok-abc`
  );
});

test('동선 최적화 미리보기 후 적용하면 패널이 닫힌다', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/days\/\d+\/optimize$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip_id: tripId,
          day_index: 1,
          ordered_poi_ids: [
            '44444444-4444-4444-8444-444444444445',
            '44444444-4444-4444-8444-444444444444',
          ],
          moves: [
            {
              poi_id: '44444444-4444-4444-8444-444444444445',
              old_sort_order: '0200',
              new_sort_order: '0050',
            },
          ],
          distance_meters: 1800,
          warnings: [],
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByRole('button', { name: '동선 최적화' }).click();

  await expect(page.getByText('최단 경로 추정 거리')).toBeVisible();
  await expect(page.getByText('1.8km')).toBeVisible();

  await page.getByRole('button', { name: '적용' }).click();
  await expect(page.getByText('최단 경로 추정 거리')).toBeHidden();
});

test('두 브라우저 컨텍스트가 presence와 WebSocket broadcast reload를 반영한다', async ({
  browser,
}) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  let titleForB = '협업 테스트 여행';
  let tripReadsForB = 0;

  try {
    await Promise.all([installControllableWebSocket(pageA), installControllableWebSocket(pageB)]);
    await commonRoutes(pageA);
    await commonRoutes(pageB, {
      getTripView: () => tripView({ title: titleForB, version: tripReadsForB + 1 }),
      onTripGet: () => {
        tripReadsForB += 1;
      },
    });

    await Promise.all([pageA.goto(`/trips/${tripId}`), pageB.goto(`/trips/${tripId}`)]);
    await Promise.all([waitForSocketCount(pageA, 1), waitForSocketCount(pageB, 1)]);

    await sendServerEvent(pageB, {
      type: 'presence.update',
      trip_id: tripId,
      payload: {
        user_id: '33333333-3333-4333-8333-333333333333',
        viewing_day: 1,
        is_online: true,
      },
    });

    await expect(pageB.getByTestId('trip-realtime-status')).toContainText('접속 1명');
    await expect(pageB.getByTestId('trip-realtime-status')).toContainText('보는 일자 1');

    titleForB = '동행이 고친 여행';
    await sendServerEvent(pageB, {
      type: 'trip.updated',
      trip_id: tripId,
      actor_user_id: '33333333-3333-4333-8333-333333333333',
      version: 2,
      payload: { title: titleForB },
    });

    await expect(pageB.getByRole('heading', { name: titleForB })).toBeVisible();
    expect(tripReadsForB).toBeGreaterThan(1);
  } finally {
    await contextA.close();
    await contextB.close();
  }
});

test('재연결 후 수신한 broadcast가 최신 HTTP snapshot으로 갱신된다', async ({ page }) => {
  let title = '협업 테스트 여행';
  let tripReads = 0;
  await installControllableWebSocket(page);
  await commonRoutes(page, {
    getTripView: () => tripView({ title, version: tripReads + 1 }),
    onTripGet: () => {
      tripReads += 1;
    },
  });

  await page.goto(`/trips/${tripId}`);
  await waitForSocketCount(page, 1);

  await closeServerSocket(page, 1012, 'service_restart');

  title = '재연결 뒤 최신 여행';
  await waitForSocketCount(page, 2);
  await expect(page.getByTestId('trip-realtime-status')).toContainText('연결됨');
  await sendServerEvent(
    page,
    {
      type: 'poi.updated',
      trip_id: tripId,
      actor_user_id: '33333333-3333-4333-8333-333333333333',
      version: 2,
      payload: { poi_id: '44444444-4444-4444-8444-444444444444' },
    }
  );

  await expect(page.getByRole('heading', { name: title })).toBeVisible();
});

test('다섯 브라우저 컨텍스트 presence fan-out와 offline cleanup을 표시한다', async ({
  browser,
}) => {
  const contexts = await Promise.all(Array.from({ length: 5 }, () => browser.newContext()));
  const pages = await Promise.all(contexts.map((context) => context.newPage()));
  const observerPage = pages[0];
  if (!observerPage) throw new Error('Observer page was not created');

  try {
    await Promise.all(
      pages.map(async (page) => {
        await installControllableWebSocket(page);
        await commonRoutes(page);
        await page.goto(`/trips/${tripId}`);
        await waitForSocketCount(page, 1);
      }),
    );

    for (let index = 1; index < pages.length; index += 1) {
      await sendServerEvent(observerPage, {
        type: 'presence.update',
        trip_id: tripId,
        payload: {
          user_id: `33333333-3333-4333-8333-33333333333${index}`,
          viewing_day: index,
          is_online: true,
        },
      });
    }

    await expect(observerPage.getByTestId('trip-realtime-status')).toContainText('접속 4명');
    await expect(observerPage.getByTestId('trip-realtime-status')).toContainText(
      '보는 일자 1, 2, 3, 4',
    );

    await sendServerEvent(observerPage, {
      type: 'presence.update',
      trip_id: tripId,
      payload: {
        user_id: '33333333-3333-4333-8333-333333333332',
        viewing_day: null,
        is_online: false,
      },
    });

    await expect(observerPage.getByTestId('trip-realtime-status')).toContainText('접속 3명');
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});
