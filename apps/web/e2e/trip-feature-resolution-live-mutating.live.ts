import { expect, test, type Page } from '@playwright/test';
import http from 'node:http';

const liveEnabled = process.env.PINVI_LIVE_FEATURE_RESOLUTION_E2E === '1';
const webBaseUrl = process.env.PINVI_LIVE_WEB_URL ?? 'http://127.0.0.1:13805';
const apiBaseUrl = process.env.PINVI_LIVE_API_URL ?? 'http://127.0.0.1:13801';
const liveEmail = process.env.PINVI_LIVE_EMAIL;
const livePassword = process.env.PINVI_LIVE_PASSWORD;
const mapProxyPort = Number(process.env.PINVI_LIVE_MAP_PROXY_PORT ?? '13701');
const mapUpstreamPort = Number(process.env.PINVI_LIVE_MAP_UPSTREAM_PORT ?? '12701');
const testPrefix = process.env.PINVI_LIVE_TRIP_PREFIX;
const foundFeatureId = process.env.PINVI_LIVE_FOUND_FEATURE_ID;
const foundFeatureName = process.env.PINVI_LIVE_FOUND_FEATURE_NAME;
const foundFeatureLon = Number(process.env.PINVI_LIVE_FOUND_FEATURE_LON);
const foundFeatureLat = Number(process.env.PINVI_LIVE_FOUND_FEATURE_LAT);
const retiredFeatureId = process.env.PINVI_LIVE_RETIRED_FEATURE_ID;
const suppressedFeatureId = process.env.PINVI_LIVE_SUPPRESSED_FEATURE_ID;
const missingFeatureId = process.env.PINVI_LIVE_MISSING_FEATURE_ID;
const weatherDate = process.env.PINVI_LIVE_WEATHER_DATE;
const weatherFeatureId = process.env.PINVI_LIVE_WEATHER_FEATURE_ID;
const weatherFeatureName = process.env.PINVI_LIVE_WEATHER_FEATURE_NAME;
const weatherFeatureLon = Number(process.env.PINVI_LIVE_WEATHER_FEATURE_LON);
const weatherFeatureLat = Number(process.env.PINVI_LIVE_WEATHER_FEATURE_LAT);
const noDataFeatureId = process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_ID;
const noDataFeatureName = process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_NAME;
const noDataFeatureLon = Number(process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LON);
const noDataFeatureLat = Number(process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LAT);
const cacheWaitMs = Number(process.env.PINVI_LIVE_FEATURE_CACHE_WAIT_MS ?? '250');
const featureCacheRevalidationConfirmed = process.env.PINVI_LIVE_FEATURE_CACHE_REVALIDATION === '1';
const longTripDayCount = 40;

type FeatureSummary = {
  feature_id: string;
  name: string;
  coord: { lon: number; lat: number } | null;
  marker_color?: string | null;
  marker_icon?: string | null;
  [key: string]: unknown;
};

type TripViewPoi = {
  feature_id: string | null;
  title: string | null;
  feature_resolution_state:
    | 'not_linked'
    | 'found'
    | 'retired'
    | 'suppressed'
    | 'missing'
    | 'unverified';
};

type TripView = {
  days: Array<{
    pois: TripViewPoi[];
    weather_by_feature_id: Record<
      string,
      {
        state: 'found' | 'no_data' | 'retired' | 'suppressed' | 'missing' | 'unavailable';
      }
    >;
  }>;
  broken_feature_count: number;
};

function apiUrl(pathname: string) {
  return new URL(pathname, apiBaseUrl).toString();
}

function offsetIsoDate(value: string, days: number) {
  const date = new Date(`${value}T00:00:00.000Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

type BrowserApiResponse = {
  body: string;
  ok: boolean;
  status: number;
};

async function browserApiRequest(
  page: Page,
  method: 'DELETE' | 'GET' | 'POST',
  pathname: string,
  data?: unknown,
): Promise<BrowserApiResponse> {
  return page.evaluate(
    async ({ body, method: requestMethod, url }) => {
      const response = await fetch(url, {
        method: requestMethod,
        credentials: 'include',
        headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return { body: await response.text(), ok: response.ok, status: response.status };
    },
    { body: data, method, url: apiUrl(pathname) },
  );
}

function responseData<T>(response: BrowserApiResponse): T {
  return (JSON.parse(response.body) as { data: T }).data;
}

function assertLiveEnv() {
  const missing = [
    ['PINVI_LIVE_WEB_URL', webBaseUrl],
    ['PINVI_LIVE_API_URL', apiBaseUrl],
    ['PINVI_LIVE_EMAIL', liveEmail],
    ['PINVI_LIVE_PASSWORD', livePassword],
    ['PINVI_LIVE_TRIP_PREFIX', testPrefix],
    ['PINVI_LIVE_FOUND_FEATURE_ID', foundFeatureId],
    ['PINVI_LIVE_FOUND_FEATURE_NAME', foundFeatureName],
    ['PINVI_LIVE_FOUND_FEATURE_LON', process.env.PINVI_LIVE_FOUND_FEATURE_LON],
    ['PINVI_LIVE_FOUND_FEATURE_LAT', process.env.PINVI_LIVE_FOUND_FEATURE_LAT],
    ['PINVI_LIVE_RETIRED_FEATURE_ID', retiredFeatureId],
    ['PINVI_LIVE_SUPPRESSED_FEATURE_ID', suppressedFeatureId],
    ['PINVI_LIVE_MISSING_FEATURE_ID', missingFeatureId],
    ['PINVI_LIVE_WEATHER_DATE', weatherDate],
    ['PINVI_LIVE_WEATHER_FEATURE_ID', weatherFeatureId],
    ['PINVI_LIVE_WEATHER_FEATURE_NAME', weatherFeatureName],
    ['PINVI_LIVE_WEATHER_FEATURE_LON', process.env.PINVI_LIVE_WEATHER_FEATURE_LON],
    ['PINVI_LIVE_WEATHER_FEATURE_LAT', process.env.PINVI_LIVE_WEATHER_FEATURE_LAT],
    ['PINVI_LIVE_WEATHER_NO_DATA_FEATURE_ID', noDataFeatureId],
    ['PINVI_LIVE_WEATHER_NO_DATA_FEATURE_NAME', noDataFeatureName],
    ['PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LON', process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LON],
    ['PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LAT', process.env.PINVI_LIVE_WEATHER_NO_DATA_FEATURE_LAT],
  ].filter(([, value]) => !value);
  if (missing.length > 0) {
    throw new Error(`${missing.map(([name]) => name).join(', ')} 환경변수가 필요합니다.`);
  }
  if (!featureCacheRevalidationConfirmed) {
    throw new Error(
      '격리 API를 짧은 TTL의 feature cache로 기동하고 PINVI_LIVE_FEATURE_CACHE_REVALIDATION=1을 설정해야 합니다.',
    );
  }
  if (
    ![
      foundFeatureLon,
      foundFeatureLat,
      weatherFeatureLon,
      weatherFeatureLat,
      noDataFeatureLon,
      noDataFeatureLat,
    ].every(Number.isFinite)
  ) {
    throw new Error('live feature 경도·위도는 유한한 실수여야 합니다.');
  }
  if (
    !Number.isInteger(mapProxyPort) ||
    !Number.isInteger(mapUpstreamPort) ||
    !Number.isInteger(cacheWaitMs) ||
    cacheWaitMs < 1
  ) {
    throw new Error('map proxy/upstream port와 cache wait는 양의 정수여야 합니다.');
  }
  if (
    new Set([
      foundFeatureId,
      retiredFeatureId,
      suppressedFeatureId,
      missingFeatureId,
      weatherFeatureId,
      noDataFeatureId,
    ]).size !== 6
  ) {
    throw new Error('live feature ID 6개는 서로 달라야 합니다.');
  }
}

async function login(page: Page) {
  await page.goto('/login');
  const emailInput = page.getByTestId('login-email');
  const passwordInput = page.getByTestId('login-password');
  await emailInput.fill(liveEmail!);
  await passwordInput.fill(livePassword!);
  const loginResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/auth/login',
  );
  await page.getByTestId('login-submit').click();
  const loginResponse = await loginResponsePromise;
  if (!loginResponse.ok()) {
    await Promise.all([
      emailInput.fill('').catch(() => undefined),
      passwordInput.fill('').catch(() => undefined),
    ]);
  }
  expect(loginResponse.ok(), `login HTTP ${loginResponse.status()}`).toBe(true);
  await expect(page).toHaveURL(/\/trips(?:[?#].*)?$/);
}

async function createTrip(page: Page, title: string) {
  await page.goto('/trips');
  const managementButton = page.getByRole('button', { name: '관리 열기' });
  if (await managementButton.isVisible()) await managementButton.click();
  await page.getByTestId('trip-create-title').fill(title);
  await page.getByTestId('trip-create-region').fill('T-VN-11/16 실데이터 검증');
  await page.getByTestId('trip-create-start').fill(weatherDate!);
  await page.getByTestId('trip-create-end').fill(offsetIsoDate(weatherDate!, longTripDayCount - 1));
  await page.getByTestId('trip-create-submit').click();
  await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();

  const link = page.getByTestId('trip-list').getByRole('link').filter({ hasText: title }).first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute('href');
  const match = href?.match(/\/trips\/([0-9a-f-]{36})/i);
  if (!match) throw new Error(`생성된 여행 링크에서 trip_id를 찾지 못했습니다: ${href ?? 'null'}`);
  return { tripId: match[1]!, href: href! };
}

async function cleanupTrip(page: Page, tripId: string) {
  const response = await browserApiRequest(page, 'DELETE', `/trips/${tripId}`, {
    mode: 'soft_delete',
  });
  if (!response.ok && response.status !== 404) {
    throw new Error(`live trip cleanup failed: HTTP ${response.status} ${response.body}`);
  }
}

async function readTrip(page: Page, tripId: string): Promise<TripView> {
  const response = await browserApiRequest(page, 'GET', `/trips/${tripId}`);
  expect(response.ok, response.body).toBe(true);
  return responseData<TripView>(response);
}

function poisByFeatureId(view: TripView) {
  return new Map(view.days.flatMap((day) => day.pois).map((poi) => [poi.feature_id, poi]));
}

function poiListItem(page: Page, name: string) {
  return page.getByTestId('trip-poi-list').locator('li').filter({ hasText: name }).first();
}

async function addFeaturePoi(
  page: Page,
  tripId: string,
  feature: FeatureSummary,
  featureId: string,
  sortOrder: string,
  dayIndex = 1,
) {
  const response = await browserApiRequest(page, 'POST', `/trips/${tripId}/pois`, {
    day_index: dayIndex,
    sort_order: sortOrder,
    feature_id: featureId,
    feature_snapshot: feature,
    source: 'feature',
    custom_marker_color: feature.marker_color ?? null,
    custom_marker_icon: feature.marker_icon ?? null,
    currency: 'KRW',
  });
  expect(response.status, response.body).toBe(201);
}

async function startMapProxy() {
  let featureOutage = false;
  let weatherOutage = false;
  type BatchRequestItem = { feature_id: string; known_row_revision?: number };
  type BatchResponseItem = { feature_id: string; state: string };
  type WeatherBatchRequestTarget = { target_at: string; feature_ids: string[] };
  const batchRequests: BatchRequestItem[][] = [];
  const batchResponses: BatchResponseItem[][] = [];
  const weatherBatchRequests: WeatherBatchRequestTarget[][] = [];
  let singleWeatherRequestCount = 0;

  const server = http.createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }
    const body = Buffer.concat(chunks);
    const isBatch = request.url?.startsWith('/v1/features/batch') ?? false;
    const isWeatherBatch = request.url?.startsWith('/v1/features/weather/batch') ?? false;
    const isSingleWeather =
      /^\/v1\/features\/[^/]+\/weather(?:\?|$)/.test(request.url ?? '') && !isWeatherBatch;
    if (isBatch && body.length > 0) {
      const parsed = JSON.parse(body.toString('utf8')) as { items?: unknown };
      if (Array.isArray(parsed.items)) {
        batchRequests.push(
          parsed.items.filter(
            (value): value is BatchRequestItem =>
              typeof value === 'object' &&
              value !== null &&
              typeof (value as { feature_id?: unknown }).feature_id === 'string',
          ),
        );
      }
    }
    if (isWeatherBatch && body.length > 0) {
      const parsed = JSON.parse(body.toString('utf8')) as { targets?: unknown };
      if (Array.isArray(parsed.targets)) {
        weatherBatchRequests.push(
          parsed.targets.filter(
            (value): value is WeatherBatchRequestTarget =>
              typeof value === 'object' &&
              value !== null &&
              typeof (value as { target_at?: unknown }).target_at === 'string' &&
              Array.isArray((value as { feature_ids?: unknown }).feature_ids) &&
              (value as { feature_ids: unknown[] }).feature_ids.every(
                (featureId) => typeof featureId === 'string',
              ),
          ),
        );
      }
    }
    if (isSingleWeather) singleWeatherRequestCount += 1;

    if (featureOutage || (weatherOutage && isWeatherBatch)) {
      response.writeHead(503, { 'content-type': 'application/problem+json', connection: 'close' });
      response.end(JSON.stringify({ code: 'LIVE_TRANSPORT_OUTAGE', title: 'live outage' }));
      return;
    }

    const headers = { ...request.headers, host: `127.0.0.1:${mapUpstreamPort}` };
    const upstream = http.request(
      {
        hostname: '127.0.0.1',
        port: mapUpstreamPort,
        method: request.method,
        path: request.url,
        headers,
      },
      (upstreamResponse) => {
        const responseChunks: Buffer[] = [];
        upstreamResponse.on('data', (chunk) => {
          responseChunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        upstreamResponse.on('end', () => {
          const responseBody = Buffer.concat(responseChunks);
          if (isBatch && (upstreamResponse.statusCode ?? 500) < 300) {
            const parsed = JSON.parse(responseBody.toString('utf8')) as {
              data?: { items?: unknown };
            };
            if (Array.isArray(parsed.data?.items)) {
              batchResponses.push(
                parsed.data.items.filter(
                  (value): value is BatchResponseItem =>
                    typeof value === 'object' &&
                    value !== null &&
                    typeof (value as { feature_id?: unknown }).feature_id === 'string' &&
                    typeof (value as { state?: unknown }).state === 'string',
                ),
              );
            }
          }
          response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
          response.end(responseBody);
        });
      },
    );
    upstream.on('error', (error) => {
      if (!response.headersSent) response.writeHead(502, { 'content-type': 'text/plain' });
      response.end(`map proxy upstream error: ${error.message}`);
    });
    if (body.length > 0) upstream.write(body);
    upstream.end();
  });

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(mapProxyPort, '127.0.0.1', () => {
      server.off('error', reject);
      resolve();
    });
  });

  return {
    batchRequests,
    batchResponses,
    weatherBatchRequests,
    get singleWeatherRequestCount() {
      return singleWeatherRequestCount;
    },
    setOutage(value: boolean) {
      featureOutage = value;
    },
    setWeatherOutage(value: boolean) {
      weatherOutage = value;
    },
    async close() {
      await new Promise<void>((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()));
      });
    },
  };
}

test.describe('Trip feature resolution live mutating flow', () => {
  test.skip(
    !liveEnabled,
    'PINVI_LIVE_FEATURE_RESOLUTION_E2E=1 일 때만 feature resolution live e2e를 실행합니다.',
  );

  test('실데이터 5상태·revision 재검증·transport 복구를 UI에서 구분한다', async ({ page }) => {
    assertLiveEnv();
    expect(new URL(webBaseUrl).origin).toBe(
      new URL(test.info().project.use.baseURL as string).origin,
    );

    const proxy = await startMapProxy();
    const title = `${testPrefix!} ${Date.now()}`;
    let tripId: string | null = null;

    try {
      await login(page);
      const created = await createTrip(page, title);
      tripId = created.tripId;
      const realFeature: FeatureSummary = {
        feature_id: foundFeatureId!,
        name: foundFeatureName!,
        coord: { lon: foundFeatureLon, lat: foundFeatureLat },
      };
      const realWeatherFeature: FeatureSummary = {
        feature_id: weatherFeatureId!,
        name: weatherFeatureName!,
        coord: { lon: weatherFeatureLon, lat: weatherFeatureLat },
      };
      const realNoDataFeature: FeatureSummary = {
        feature_id: noDataFeatureId!,
        name: noDataFeatureName!,
        coord: { lon: noDataFeatureLon, lat: noDataFeatureLat },
      };

      await addFeaturePoi(page, tripId, realFeature, realFeature.feature_id, 'a0');
      await addFeaturePoi(page, tripId, realWeatherFeature, realWeatherFeature.feature_id, 'a01');
      await addFeaturePoi(page, tripId, realNoDataFeature, realNoDataFeature.feature_id, 'a02');
      for (let dayIndex = 2; dayIndex <= longTripDayCount; dayIndex += 1) {
        await addFeaturePoi(
          page,
          tripId,
          realWeatherFeature,
          realWeatherFeature.feature_id,
          'a0',
          dayIndex,
        );
      }
      await addFeaturePoi(
        page,
        tripId,
        { ...realFeature, name: 'retired 실데이터 저장본' },
        retiredFeatureId!,
        'a1',
      );
      await addFeaturePoi(
        page,
        tripId,
        { ...realFeature, name: 'suppressed 실데이터 저장본' },
        suppressedFeatureId!,
        'a2',
      );
      await addFeaturePoi(
        page,
        tripId,
        { ...realFeature, name: 'missing exact 저장본' },
        missingFeatureId!,
        'a3',
      );

      await page.goto(created.href);
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expect(page.getByText(realFeature.name).first()).toBeVisible();
      await expect(page.getByLabel('종료된 장소 정보').first()).toBeVisible();
      await expect(page.getByLabel('비공개 장소 정보').first()).toBeVisible();
      await expect(page.getByLabel('장소 정보 사용 불가').first()).toBeVisible();
      await expect(page.getByText('정보 사용 불가 2곳').first()).toBeVisible();
      const tripMap = page.getByRole('region', { name: '여행 지도' });
      await expect(tripMap.getByText(`${longTripDayCount}일 표시`, { exact: true })).toBeVisible();
      await expect(
        tripMap.getByText(`장소 ${longTripDayCount + 5}곳`, { exact: true }),
      ).toBeVisible();
      await expect(page.getByText(/라이브러리에서 삭제된 장소/)).toHaveCount(0);
      const weatherPoiItem = poiListItem(page, realWeatherFeature.name);
      const noDataPoiItem = poiListItem(page, realNoDataFeature.name);
      const retiredPoiItem = poiListItem(page, 'retired 실데이터 저장본');
      const suppressedPoiItem = poiListItem(page, 'suppressed 실데이터 저장본');
      const missingPoiItem = poiListItem(page, 'missing exact 저장본');
      const weatherSummary = weatherPoiItem.getByTestId('trip-weather-summary');
      await expect(weatherSummary).toBeVisible();
      await expect(weatherSummary).toContainText(/기온|하늘|강수|습도|바람|미세/);
      await expect(noDataPoiItem).toContainText('이 날짜의 날씨 정보가 없습니다.');
      await expect(
        retiredPoiItem.getByText('장소 상태가 종료되어 날씨를 확인할 수 없습니다.'),
      ).toBeVisible();
      await expect(
        suppressedPoiItem.getByText('비공개 장소는 날씨를 확인할 수 없습니다.'),
      ).toBeVisible();
      await expect(
        missingPoiItem.getByText('장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.'),
      ).toBeVisible();

      const weatherBatchCountBeforeDirectRead = proxy.weatherBatchRequests.length;
      const healthy = await readTrip(page, tripId);
      expect(proxy.weatherBatchRequests).toHaveLength(weatherBatchCountBeforeDirectRead + 1);
      const healthyPois = poisByFeatureId(healthy);
      expect(healthyPois.get(realFeature.feature_id)?.feature_resolution_state).toBe('found');
      expect(healthyPois.get(retiredFeatureId!)?.feature_resolution_state).toBe('retired');
      expect(healthyPois.get(suppressedFeatureId!)?.feature_resolution_state).toBe('suppressed');
      expect(healthyPois.get(missingFeatureId!)?.feature_resolution_state).toBe('missing');
      expect(healthy.broken_feature_count).toBe(2);
      const healthyWeather = healthy.days[0]!.weather_by_feature_id;
      expect(healthyWeather[weatherFeatureId!]?.state).toBe('found');
      expect(healthyWeather[noDataFeatureId!]?.state).toBe('no_data');
      expect(healthyWeather[retiredFeatureId!]?.state).toBe('retired');
      expect(healthyWeather[suppressedFeatureId!]?.state).toBe('suppressed');
      expect(healthyWeather[missingFeatureId!]?.state).toBe('missing');
      expect(healthy.days).toHaveLength(longTripDayCount);
      expect(
        healthy.days.every((day) => {
          const state = day.weather_by_feature_id[weatherFeatureId!]?.state;
          return state === 'found' || state === 'no_data';
        }),
      ).toBe(true);
      expect(
        proxy.weatherBatchRequests.some(
          (targets) =>
            targets.length === longTripDayCount &&
            targets[0]?.feature_ids.includes(weatherFeatureId!) &&
            targets[0]?.feature_ids.includes(noDataFeatureId!),
        ),
      ).toBe(true);
      expect(
        proxy.weatherBatchRequests.every((targets) =>
          targets.every(
            ({ feature_ids: featureIds }) =>
              !featureIds.includes(retiredFeatureId!) &&
              !featureIds.includes(suppressedFeatureId!) &&
              !featureIds.includes(missingFeatureId!),
          ),
        ),
      ).toBe(true);
      expect(proxy.singleWeatherRequestCount).toBe(0);

      const finalDayTab = page.getByRole('tab', { name: `${longTripDayCount}일차` });
      await finalDayTab.click();
      const finalDayCard = finalDayTab.locator('xpath=ancestor::article');
      await expect(finalDayCard.getByText(realWeatherFeature.name)).toBeVisible();
      await expect(finalDayCard).not.toContainText(
        '여행 날짜가 많아 이 날짜의 날씨는 표시하지 않습니다.',
      );
      await expect(finalDayCard).not.toContainText('날씨 서비스를 일시적으로 사용할 수 없습니다.');

      const healthyWeatherBatchCount = proxy.weatherBatchRequests.length;
      proxy.setWeatherOutage(true);
      await page.reload();
      await expect(
        weatherPoiItem.getByText('날씨 서비스를 일시적으로 사용할 수 없습니다.'),
      ).toBeVisible();
      expect(proxy.weatherBatchRequests.length).toBeGreaterThan(healthyWeatherBatchCount);
      const weatherOutage = await readTrip(page, tripId);
      expect(weatherOutage.days[0]!.weather_by_feature_id[weatherFeatureId!]?.state).toBe(
        'unavailable',
      );
      expect(weatherOutage.days[0]!.weather_by_feature_id[noDataFeatureId!]?.state).toBe(
        'unavailable',
      );
      expect(weatherOutage.days[0]!.weather_by_feature_id[retiredFeatureId!]?.state).toBe(
        'retired',
      );
      expect(proxy.singleWeatherRequestCount).toBe(0);

      proxy.setWeatherOutage(false);
      await page.reload();
      await expect(weatherSummary).toBeVisible();
      await expect(weatherSummary).toContainText(/기온|하늘|강수|습도|바람|미세/);
      await expect(noDataPoiItem).toContainText('이 날짜의 날씨 정보가 없습니다.');
      expect(
        proxy.batchRequests.some((items) =>
          items.some((item) => item.feature_id === missingFeatureId),
        ),
      ).toBe(true);
      const healthyBatchCount = proxy.batchRequests.length;

      await page.waitForTimeout(cacheWaitMs);
      await page.reload();
      await expect(page.getByText(realFeature.name).first()).toBeVisible();
      expect(proxy.batchRequests.length).toBeGreaterThan(healthyBatchCount);
      expect(
        proxy.batchRequests
          .slice(healthyBatchCount)
          .some((items) =>
            items.some(
              (item) =>
                item.feature_id === realFeature.feature_id &&
                typeof item.known_row_revision === 'number',
            ),
          ),
      ).toBe(true);
      expect(
        proxy.batchResponses.some((items) =>
          items.some(
            (item) => item.feature_id === realFeature.feature_id && item.state === 'unchanged',
          ),
        ),
      ).toBe(true);
      const revalidatedBatchCount = proxy.batchRequests.length;

      await page.waitForTimeout(cacheWaitMs);
      proxy.setOutage(true);
      await page.reload();
      await expect(page.getByLabel('저장된 정보 · 최신 상태 확인 실패').first()).toBeVisible();
      await expect(page.getByText(realFeature.name).first()).toBeVisible();
      await expect(page.getByText(/정보 사용 불가 [0-9]+곳/)).toHaveCount(0);
      expect(proxy.batchRequests.length).toBeGreaterThan(revalidatedBatchCount);
      const outageBatchCount = proxy.batchRequests.length;
      const outage = await readTrip(page, tripId);
      const outagePois = poisByFeatureId(outage);
      expect(outagePois.get(realFeature.feature_id)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(retiredFeatureId!)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(suppressedFeatureId!)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(missingFeatureId!)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(weatherFeatureId!)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(noDataFeatureId!)?.feature_resolution_state).toBe('unverified');
      expect(outage.broken_feature_count).toBe(0);

      proxy.setOutage(false);
      await page.reload();
      await expect(page.getByLabel('종료된 장소 정보').first()).toBeVisible();
      await expect(page.getByLabel('비공개 장소 정보').first()).toBeVisible();
      await expect(page.getByLabel('장소 정보 사용 불가').first()).toBeVisible();
      await expect(page.getByText('정보 사용 불가 2곳').first()).toBeVisible();
      expect(proxy.batchRequests.length).toBeGreaterThan(outageBatchCount);
      const recovered = await readTrip(page, tripId);
      const recoveredPois = poisByFeatureId(recovered);
      expect(recoveredPois.get(realFeature.feature_id)?.feature_resolution_state).toBe('found');
      expect(recoveredPois.get(retiredFeatureId!)?.feature_resolution_state).toBe('retired');
      expect(recoveredPois.get(suppressedFeatureId!)?.feature_resolution_state).toBe('suppressed');
      expect(recoveredPois.get(missingFeatureId!)?.feature_resolution_state).toBe('missing');
      expect(recoveredPois.get(weatherFeatureId!)?.feature_resolution_state).toBe('found');
      expect(recoveredPois.get(noDataFeatureId!)?.feature_resolution_state).toBe('found');
      expect(recovered.broken_feature_count).toBe(2);
      expect(recovered.days[0]!.weather_by_feature_id[weatherFeatureId!]?.state).toBe('found');
      expect(recovered.days[0]!.weather_by_feature_id[noDataFeatureId!]?.state).toBe('no_data');
      expect(proxy.singleWeatherRequestCount).toBe(0);
    } finally {
      proxy.setOutage(false);
      proxy.setWeatherOutage(false);
      try {
        if (tripId) await cleanupTrip(page, tripId);
      } finally {
        await proxy.close();
      }
    }
  });
});
