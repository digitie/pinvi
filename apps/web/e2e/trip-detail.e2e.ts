import { expect, test, type Page } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const poiId = '44444444-4444-4444-8444-444444444444';
const snapshotPoiId = '44444444-4444-4444-8444-444444444445';
const brokenPoiId = '44444444-4444-4444-8444-444444444446';
const companionId = '55555555-5555-4555-8555-555555555555';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const TRIP_VIEW = {
  trip: {
    trip_id: tripId,
    owner_user_id: userId,
    title: '부산 2박 3일',
    description: null,
    region_hint: '부산',
    primary_region_code: '26',
    primary_region_source: 'manual',
    start_date: '2026-07-01',
    end_date: '2026-07-03',
    visibility: 'private',
    status: 'planned',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  },
  days: [
    {
      day_index: 1,
      date: '2026-07-01',
      title: '1일차',
      pois: [
        {
          poi_id: poiId,
          feature_id: 'feat-haeundae',
          sort_order: '0100',
          title: '해운대 해수욕장',
          feature: { coord: { lon: 129.16, lat: 35.158 } },
          marker_color: 'P-07',
          marker_icon: 'swimming',
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
        },
      ],
    },
  ],
  companions: [
    {
      companion_id: companionId,
      trip_id: tripId,
      user_id: null,
      invited_email: 'friend@example.com',
      invited_nickname: '동행',
      role: 'editor',
      invited_at: '2026-06-01T09:00:00+09:00',
      joined_at: null,
      created_at: '2026-06-01T09:00:00+09:00',
      updated_at: '2026-06-01T09:00:00+09:00',
    },
  ],
  share_links: [],
  broken_feature_count: 0,
};

const BASE_MARKER_DAY = TRIP_VIEW.days[0]!;
const BASE_MARKER_POI = BASE_MARKER_DAY.pois[0]!;
const DAY_ATTACHMENT = {
  attachment_id: '66666666-6666-4666-8666-666666666666',
  trip_id: tripId,
  trip_poi_id: null,
  source_attachment_id: null,
  bucket: 'pinvi-media',
  storage_key: 'user-uploads/trip_day_attachment/u/2026/07/day-plan.pdf',
  original_filename: 'day-plan.pdf',
  content_type: 'application/pdf',
  byte_size: 2048,
  public_url: null,
  role: 'document',
  description: null,
  sort_order: 0,
  created_at: '2026-06-01T09:00:00+09:00',
  updated_at: '2026-06-01T09:00:00+09:00',
};
const POI_ATTACHMENT = {
  ...DAY_ATTACHMENT,
  attachment_id: '77777777-7777-4777-8777-777777777777',
  trip_poi_id: poiId,
  storage_key: 'user-uploads/poi_attachment/u/2026/07/ticket.jpg',
  original_filename: 'ticket.jpg',
  content_type: 'image/jpeg',
  byte_size: 1024,
  role: 'image',
};

const MARKER_VIEW = {
  ...TRIP_VIEW,
  days: [
    {
      ...BASE_MARKER_DAY,
      pois: [
        {
          ...BASE_MARKER_POI,
          title: '해운대 custom',
          feature: {
            coord: { lon: 129.16, lat: 35.158 },
            marker_color: 'P-07',
            marker_icon: 'swimming',
            category: '해수욕장',
          },
          marker_color: 'P-10',
          marker_icon: 'lodging',
        },
        {
          ...BASE_MARKER_POI,
          poi_id: snapshotPoiId,
          feature_id: 'feat-heritage',
          title: '국가유산 snapshot',
          feature: {
            coord: { lon: 126.977, lat: 37.5796 },
            marker_color: 'P-03',
            marker_icon: 'monument',
            category: '국가유산',
          },
          marker_color: null,
          marker_icon: null,
        },
        {
          ...BASE_MARKER_POI,
          poi_id: brokenPoiId,
          feature_id: 'feat-notice-broken',
          title: '공지 broken',
          feature: { coord: { lon: 127.02, lat: 37.56 }, category: '공지' },
          marker_color: null,
          marker_icon: null,
          is_broken: true,
          feature_link_broken_at: '2026-06-28T09:00:00+09:00',
        },
      ],
    },
  ],
  broken_feature_count: 1,
};

const LAYER_VIEW = {
  ...TRIP_VIEW,
  days: [
    BASE_MARKER_DAY,
    {
      ...BASE_MARKER_DAY,
      day_index: 2,
      date: '2026-07-02',
      title: '2일차',
      pois: [
        {
          ...BASE_MARKER_POI,
          poi_id: snapshotPoiId,
          feature_id: 'feat-gamcheon',
          title: '감천문화마을',
          feature: {
            coord: { lon: 129.01, lat: 35.1 },
            marker_color: 'P-04',
            marker_icon: 'camera',
            category: '마을',
          },
          marker_color: 'P-04',
          marker_icon: 'camera',
        },
      ],
    },
  ],
};

type MutableTripDetailView = Omit<typeof TRIP_VIEW, 'trip' | 'days'> & {
  trip: Omit<typeof TRIP_VIEW.trip, 'start_date' | 'end_date'> & {
    start_date: string | null;
    end_date: string | null;
  };
  days: unknown[];
};

interface MockTripDetailOptions {
  attachmentsByPath?: (pathname: string) => unknown[];
  weatherByFeatureId?: Record<string, unknown>;
}

async function mockTripDetailRoutes(
  page: Page,
  tripView: unknown | (() => unknown) = TRIP_VIEW,
  options: MockTripDetailOptions = {},
) {
  await page.route(/.*\/auth\/refresh$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { user_id: userId } }),
    });
  });

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

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/.*attachments(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    const pathname = new URL(request.url()).pathname;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: options.attachmentsByPath?.(pathname) ?? [] }),
    });
  });

  await page.route(/.*\/features\/[^/]+\/weather(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    const parts = new URL(request.url()).pathname.split('/');
    const featureId = decodeURIComponent(parts[parts.length - 2] ?? '');
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: options.weatherByFeatureId?.[featureId] ?? {
          feature_id: featureId,
          asof: null,
          latest_at: null,
          is_stale: false,
          source_styles: [],
          metrics: [],
        },
      }),
    });
  });

  await page.route(/.*\/users\/me\/telegram-targets$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/telegram-targets$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: typeof tripView === 'function' ? tripView() : tripView }),
    });
  });
}

async function expectTripMapSurface(page: Page) {
  const fallback = page.getByTestId('vworld-map-fallback');
  const canvas = page.locator('.maplibregl-canvas').first();

  if (process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS === '1') {
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    const box = await canvas.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThan(300);
    expect(box?.height ?? 0).toBeGreaterThan(300);
    await expect(fallback).toHaveCount(0);
    return;
  }

  await expect(fallback.or(canvas)).toBeVisible({ timeout: 20_000 });
}

async function expectMyMapsDetailLayout(page: Page) {
  const panel = page.getByTestId('trip-detail-panel');
  const map = page.getByTestId('trip-detail-map');

  await expect(panel).toBeVisible();
  await expect(map).toBeVisible();

  const panelBox = await panel.boundingBox();
  const mapBox = await map.boundingBox();
  expect(panelBox).not.toBeNull();
  expect(mapBox).not.toBeNull();
  expect(panelBox?.x ?? 0).toBeLessThan(mapBox?.x ?? 0);
  expect(mapBox?.width ?? 0).toBeGreaterThan(panelBox?.width ?? 0);
  expect(mapBox?.height ?? 0).toBeGreaterThan(500);
}

async function expectMobileDrawerLayout(page: Page) {
  const panel = page.getByTestId('trip-detail-panel');
  const map = page.getByTestId('trip-detail-map');

  await expect(panel).toBeVisible();
  await expect(map).toBeVisible();

  const panelBox = await panel.boundingBox();
  const mapBox = await map.boundingBox();
  expect(panelBox).not.toBeNull();
  expect(mapBox).not.toBeNull();
  expect(panelBox?.x ?? 0).toBeGreaterThanOrEqual(mapBox?.x ?? 0);
  expect(panelBox?.x ?? 0).toBeLessThan((mapBox?.x ?? 0) + 4);
  expect(panelBox?.y ?? 0).toBeGreaterThanOrEqual((mapBox?.y ?? 0) - 1);
  expect(panelBox?.width ?? 0).toBeLessThan(mapBox?.width ?? 0);
  expect(mapBox?.height ?? 0).toBeGreaterThan(500);
}

async function expectMobileMapFirstLayout(page: Page) {
  const topPanel = page.getByTestId('trip-top-panel');
  const map = page.getByTestId('trip-detail-map');

  await expect(topPanel).toBeVisible();
  await expect(map).toBeVisible();
  await expect(page.getByLabel('사용자 메뉴')).toHaveCount(0);

  const topPanelBox = await topPanel.boundingBox();
  const mapBox = await map.boundingBox();
  expect(topPanelBox).not.toBeNull();
  expect(mapBox).not.toBeNull();
  expect(topPanelBox?.height ?? 999).toBeLessThan(72);
  expect(mapBox?.y ?? 999).toBeLessThan(4);
  expect(mapBox?.height ?? 0).toBeGreaterThan(850);
}

async function installClosingWebSocket(page: Page, code: number, reason: string) {
  await page.addInitScript(
    ({ closeCode, closeReason }) => {
      class ClosingWebSocket extends EventTarget {
        static readonly CONNECTING = 0;
        static readonly OPEN = 1;
        static readonly CLOSING = 2;
        static readonly CLOSED = 3;

        readonly url: string;
        readyState = ClosingWebSocket.CONNECTING;

        constructor(url: string) {
          super();
          this.url = url;
          window.setTimeout(() => {
            this.readyState = ClosingWebSocket.OPEN;
            this.dispatchEvent(new Event('open'));
            window.setTimeout(() => {
              this.readyState = ClosingWebSocket.CLOSED;
              this.dispatchEvent(
                new CloseEvent('close', {
                  code: closeCode,
                  reason: closeReason,
                  wasClean: false,
                }),
              );
            }, 20);
          }, 0);
        }

        send() {}

        close() {
          this.readyState = ClosingWebSocket.CLOSED;
          this.dispatchEvent(
            new CloseEvent('close', { code: 1000, reason: 'manual', wasClean: true }),
          );
        }
      }

      window.WebSocket = ClosingWebSocket as unknown as typeof WebSocket;
    },
    { closeCode: code, closeReason: reason },
  );
}

test('trip 상세가 TripView를 받아 헤더·POI·협업 섹션을 렌더링한다', async ({ page }) => {
  await mockTripDetailRoutes(page);

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByTestId('trip-detail-shell')).toBeVisible();
  await expect(page.getByTestId('trip-top-panel')).toBeVisible();
  await expectMyMapsDetailLayout(page);
  await expectTripMapSurface(page);
  await expect(page.getByRole('heading', { name: '부산 2박 3일' })).toBeVisible();
  await expect(page.getByTestId('trip-layer-list')).toContainText('지도 레이어');
  await expect(page.getByRole('tab', { name: '1일차' })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '1일차 표시' })).toBeChecked();
  await expect(page.getByTestId('trip-map-place-search')).toBeVisible();
  await expect(page.getByTestId('trip-detail-map').locator('aside')).toHaveCount(0);
  await expect(page.getByTestId('trip-poi-list')).toContainText('해운대 해수욕장');

  await page.getByRole('tab', { name: /동행/ }).click();
  await expect(page.getByTestId('companion-list')).toContainText('동행');
  await page.getByRole('tab', { name: '공유' }).click();
  await expect(page.getByTestId('trip-detail-panel')).toContainText('공유 링크');
  await page.getByRole('tab', { name: '파일' }).click();
  await expect(page.getByTestId('trip-detail-panel')).toContainText('첨부');
  await page.getByRole('tab', { name: '댓글' }).click();
  await expect(page.getByTestId('trip-detail-panel')).toContainText('댓글');
});

test.describe('Samsung Internet 모바일 상세 레이아웃', () => {
  test.use({
    viewport: { width: 1180, height: 915 },
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36',
  });

  test('큰 layout viewport에서도 상단 메뉴만 남기고 상세 패널을 왼쪽 드로어로 연다', async ({
    page,
  }) => {
    await mockTripDetailRoutes(page);

    await page.goto(`/trips/${tripId}`);

    await expectMobileMapFirstLayout(page);
    await expect(page.getByRole('button', { name: '패널 열기' })).toBeVisible();
    await expect(page.getByRole('button', { name: '패널 접기' })).toBeHidden();
    await expect(page.getByTestId('trip-detail-panel')).toBeHidden();
    await expect(page.getByTestId('trip-detail-map')).toBeVisible();
    await page.getByRole('button', { name: '패널 열기' }).click();
    await expectMobileDrawerLayout(page);
    await expect(page.getByTestId('trip-detail-panel')).toContainText('지도 레이어');
    await page.getByRole('button', { name: /해운대 해수욕장/ }).first().click();
    await expect(page.getByTestId('trip-detail-panel')).toBeHidden();
    await expect(
      page.locator(`[data-testid="trip-map-marker-style"][data-poi-id="${poiId}"]`),
    ).toHaveAttribute('data-marker-selected', 'true');
  });
});

test('상세 지도는 왼쪽 일자 레이어 표시 상태만 반영하고 오른쪽 패널을 두지 않는다', async ({
  page,
}) => {
  await mockTripDetailRoutes(page, LAYER_VIEW);

  await page.goto(`/trips/${tripId}`);

  const secondMarker = page.locator(
    `[data-testid="trip-map-marker-style"][data-poi-id="${snapshotPoiId}"]`,
  );
  await expect(secondMarker).toHaveText('감천문화마을');
  await page.getByRole('checkbox', { name: '2일차 표시' }).uncheck();
  await expect(secondMarker).toHaveCount(0);
  await expect(page.getByTestId('trip-detail-map').locator('aside')).toHaveCount(0);
});

test('여행 지도 marker는 resolved/snapshot/category와 selected/broken 상태를 노출한다', async ({
  page,
}) => {
  await mockTripDetailRoutes(page, MARKER_VIEW);

  await page.goto(`/trips/${tripId}`);

  const custom = page.locator(`[data-testid="trip-map-marker-style"][data-poi-id="${poiId}"]`);
  const snapshot = page.locator(
    `[data-testid="trip-map-marker-style"][data-poi-id="${snapshotPoiId}"]`,
  );
  const broken = page.locator(
    `[data-testid="trip-map-marker-style"][data-poi-id="${brokenPoiId}"]`,
  );

  await expect(custom).toHaveAttribute('data-marker-color', 'P-10');
  await expect(custom).toHaveAttribute('data-marker-icon', 'lodging');
  await expect(custom).toHaveAttribute('data-marker-source', 'resolved');

  await expect(snapshot).toHaveAttribute('data-marker-color', 'P-03');
  await expect(snapshot).toHaveAttribute('data-marker-icon', 'monument');
  await expect(snapshot).toHaveAttribute('data-marker-source', 'snapshot');
  await expect(snapshot).toHaveAttribute('data-marker-category', '국가유산');

  await expect(broken).toHaveAttribute('data-marker-color', 'P-14');
  await expect(broken).toHaveAttribute('data-marker-icon', 'alert');
  await expect(broken).toHaveAttribute('data-marker-source', 'category');
  await expect(broken).toHaveAttribute('data-marker-broken', 'true');

  await page.getByRole('button', { name: /해운대 custom/ }).click();
  await expect(custom).toHaveAttribute('data-marker-selected', 'true');
});

test('여행 기간보다 많은 일자는 추가할 수 없다', async ({ page }) => {
  await mockTripDetailRoutes(page, {
    ...TRIP_VIEW,
    trip: {
      ...TRIP_VIEW.trip,
      start_date: '2026-07-01',
      end_date: '2026-07-01',
    },
  });

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByTestId('trip-add-layer')).toBeDisabled();
  await expect(page.getByTestId('trip-add-day-inline')).toBeDisabled();
  await expect(page.getByTestId('trip-top-panel')).toContainText(
    '여행 기간은 최대 1일입니다. 기간을 먼저 늘려주세요.',
  );
});

test('날짜가 없는 여행도 Day Plan 내부 버튼으로 일자를 추가할 수 있다', async ({ page }) => {
  let currentView: MutableTripDetailView = {
    ...TRIP_VIEW,
    trip: {
      ...TRIP_VIEW.trip,
      start_date: null,
      end_date: null,
    },
    days: [],
  };

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/days$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    const body = request.postDataJSON() as { day_index: number; date?: string | null };
    const day = {
      trip_id: tripId,
      day_index: body.day_index,
      date: body.date ?? null,
      title: null,
      note: null,
      version: 1,
      created_at: '2026-06-01T09:00:00+09:00',
      updated_at: '2026-06-01T09:00:00+09:00',
    };
    currentView = {
      ...currentView,
      days: [{ ...day, pois: [] }],
    };
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: day }),
    });
  });
  await mockTripDetailRoutes(page, () => currentView);

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByTestId('trip-layer-list')).toContainText('아직 일정 레이어가 없습니다.');
  await page.getByTestId('trip-add-day-inline').click();
  await expect(page.getByRole('tab', { name: '1일차' })).toBeVisible();
  await expect(page.getByTestId('trip-layer-list')).toContainText('미정');
});

test('Day Plan 안에서 날짜·장소 파일과 날짜에 맞는 날씨를 보여준다', async ({ page }) => {
  await mockTripDetailRoutes(page, TRIP_VIEW, {
    attachmentsByPath: (pathname) => {
      if (pathname.endsWith('/days/1/attachments')) return [DAY_ATTACHMENT];
      if (pathname.endsWith(`/pois/${poiId}/attachments`)) return [POI_ATTACHMENT];
      return [];
    },
    weatherByFeatureId: {
      'feat-haeundae': {
        feature_id: 'feat-haeundae',
        asof: '2026-07-01T09:00:00+09:00',
        latest_at: '2026-07-01T09:00:00+09:00',
        is_stale: false,
        source_styles: ['observed', 'short'],
        metrics: [
          {
            metric_key: 'T1H',
            metric_name: '기온',
            forecast_style: 'observed',
            timeline_bucket: 'now',
            valid_at: null,
            issued_at: null,
            observed_at: '2026-07-01T09:00:00+09:00',
            value_number: 24,
            value_text: null,
            unit: '℃',
            severity: null,
          },
          {
            metric_key: 'TMP',
            metric_name: '기온',
            forecast_style: 'short',
            timeline_bucket: 'forecast',
            valid_at: '2026-07-01T15:00:00+09:00',
            issued_at: '2026-07-01T05:00:00+09:00',
            observed_at: null,
            value_number: 27,
            value_text: null,
            unit: '℃',
            severity: null,
          },
          {
            metric_key: 'PM10',
            metric_name: '미세',
            forecast_style: 'observed',
            timeline_bucket: 'now',
            valid_at: null,
            issued_at: null,
            observed_at: '2026-07-01T09:00:00+09:00',
            value_number: 32,
            value_text: null,
            unit: '㎍/㎥',
            severity: '보통',
          },
          {
            metric_key: 'TMP',
            metric_name: '기온',
            forecast_style: 'short',
            timeline_bucket: 'forecast',
            valid_at: '2026-07-02T15:00:00+09:00',
            issued_at: '2026-07-01T05:00:00+09:00',
            observed_at: null,
            value_number: 99,
            value_text: null,
            unit: '℃',
            severity: null,
          },
        ],
      },
    },
  });

  await page.goto(`/trips/${tripId}`);

  const plan = page.getByTestId('trip-layer-list');
  await expect(plan).toContainText('day-plan.pdf');
  await expect(plan).toContainText('ticket.jpg');
  await expect(plan).toContainText('현재');
  await expect(plan).toContainText('예보');
  await expect(plan).toContainText('미세먼지');
  await expect(plan).not.toContainText('99℃');
});

test('실시간 권한 상실 close는 안내와 여행 목록 이동 링크를 보여준다', async ({ page }) => {
  await installClosingWebSocket(page, 4403, 'permission_denied');
  await mockTripDetailRoutes(page);

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByTestId('trip-realtime-status')).toContainText('권한 없음');
  await expect(page.getByTestId('trip-realtime-permission-lost')).toContainText(
    '여행 접근 권한이 사라져 실시간 연결을 종료했습니다.',
  );
  await expect(page.getByRole('link', { name: '여행 목록으로 이동' })).toHaveAttribute(
    'href',
    '/trips',
  );
});

test('실시간 rate limit close는 backoff 안내를 보여준다', async ({ page }) => {
  await installClosingWebSocket(page, 4429, 'rate_limited');
  await mockTripDetailRoutes(page);

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByTestId('trip-realtime-status')).toContainText(/속도 제한|재연결 대기/);
  await expect(page.getByTestId('trip-realtime-backoff-notice')).toContainText(
    '실시간 연결을 잠시 늦춰 다시 시도합니다.',
  );
});
