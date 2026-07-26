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
const featureCacheDisabledConfirmed = process.env.PINVI_LIVE_FEATURE_CACHE_DISABLED === '1';

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
  feature_resolution_state: 'not_linked' | 'found' | 'missing' | 'unverified';
};

type TripView = {
  days: Array<{ pois: TripViewPoi[] }>;
  broken_feature_count: number;
};

function apiUrl(pathname: string) {
  return new URL(pathname, apiBaseUrl).toString();
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
  ].filter(([, value]) => !value);
  if (missing.length > 0) {
    throw new Error(`${missing.map(([name]) => name).join(', ')} 환경변수가 필요합니다.`);
  }
  if (!featureCacheDisabledConfirmed) {
    throw new Error(
      '격리 API를 PINVI_FEATURE_CACHE_ENABLED=false로 기동하고 PINVI_LIVE_FEATURE_CACHE_DISABLED=1을 설정해야 합니다.',
    );
  }
  if (!Number.isInteger(mapProxyPort) || !Number.isInteger(mapUpstreamPort)) {
    throw new Error('map proxy/upstream port는 정수여야 합니다.');
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
  await page.getByTestId('trip-create-region').fill('T-VN-08 실데이터 검증');
  await page.getByTestId('trip-create-start').fill('2026-12-01');
  await page.getByTestId('trip-create-end').fill('2026-12-01');
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

async function findRealFeature(page: Page): Promise<FeatureSummary> {
  const response = await browserApiRequest(
    page,
    'GET',
    '/features/nearby?lon=126.978&lat=37.5665&radius_m=1000&limit=50',
  );
  expect(response.ok, response.body).toBe(true);
  const items = responseData<FeatureSummary[]>(response);
  const feature = items.find(
    (item) =>
      typeof item.feature_id === 'string' &&
      item.feature_id.length > 0 &&
      typeof item.name === 'string' &&
      item.name.length > 0 &&
      item.coord !== null,
  );
  if (!feature) throw new Error('서울 반경 실데이터에서 좌표가 있는 feature를 찾지 못했습니다.');
  return feature;
}

async function addFeaturePoi(
  page: Page,
  tripId: string,
  feature: FeatureSummary,
  featureId: string,
  sortOrder: string,
) {
  const response = await browserApiRequest(page, 'POST', `/trips/${tripId}/pois`, {
    day_index: 1,
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
  let outage = false;
  const batchRequests: string[][] = [];

  const server = http.createServer(async (request, response) => {
    const chunks: Buffer[] = [];
    for await (const chunk of request) {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
    }
    const body = Buffer.concat(chunks);
    if (request.url?.startsWith('/v1/features/batch') && body.length > 0) {
      const parsed = JSON.parse(body.toString('utf8')) as { feature_ids?: unknown };
      if (Array.isArray(parsed.feature_ids)) {
        batchRequests.push(
          parsed.feature_ids.filter((value): value is string => typeof value === 'string'),
        );
      }
    }

    if (outage) {
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
        response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
        upstreamResponse.pipe(response);
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
    setOutage(value: boolean) {
      outage = value;
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

  test('실데이터 found/missing과 transport outage/recovery를 UI에서 구분한다', async ({ page }) => {
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
      const realFeature = await findRealFeature(page);
      const opaqueFeatureId = `${realFeature.feature_id}@codex-live`;

      await addFeaturePoi(page, tripId, realFeature, realFeature.feature_id, 'a0');
      await addFeaturePoi(
        page,
        tripId,
        { ...realFeature, name: 'opaque exact 저장본' },
        opaqueFeatureId,
        'a1',
      );

      await page.goto(created.href);
      await expect(page.getByRole('heading', { name: title })).toBeVisible();
      await expect(page.getByText(realFeature.name).first()).toBeVisible();
      await expect(page.getByLabel('장소 정보 사용 불가').first()).toBeVisible();
      await expect(page.getByText('정보 사용 불가 1곳').first()).toBeVisible();
      await page
        .getByTestId('trip-poi-list')
        .getByRole('button', { name: /opaque exact 저장본/ })
        .click();
      await expect(page.getByText('장소 정보 사용 불가', { exact: true })).toBeVisible();
      await expect(page.getByText(/라이브러리에서 삭제된 장소/)).toHaveCount(0);

      const healthy = await readTrip(page, tripId);
      const healthyPois = poisByFeatureId(healthy);
      expect(healthyPois.get(realFeature.feature_id)?.feature_resolution_state).toBe('found');
      expect(healthyPois.get(opaqueFeatureId)?.feature_resolution_state).toBe('missing');
      expect(healthy.broken_feature_count).toBe(1);
      expect(proxy.batchRequests.some((ids) => ids.includes(opaqueFeatureId))).toBe(true);
      const healthyBatchCount = proxy.batchRequests.length;

      proxy.setOutage(true);
      await page.reload();
      await expect(page.getByLabel('저장된 정보 · 최신 상태 확인 실패').first()).toBeVisible();
      await expect(page.getByText(realFeature.name).first()).toBeVisible();
      await expect(page.getByText(/정보 사용 불가 1곳/)).toHaveCount(0);
      await page
        .getByTestId('trip-poi-list')
        .getByRole('button', { name: realFeature.name })
        .first()
        .click();
      await expect(
        page.getByText('저장된 정보 · 최신 상태 확인 실패', { exact: true }),
      ).toBeVisible();
      expect(proxy.batchRequests.length).toBeGreaterThan(healthyBatchCount);
      const outageBatchCount = proxy.batchRequests.length;
      const outage = await readTrip(page, tripId);
      const outagePois = poisByFeatureId(outage);
      expect(outagePois.get(realFeature.feature_id)?.feature_resolution_state).toBe('unverified');
      expect(outagePois.get(opaqueFeatureId)?.feature_resolution_state).toBe('unverified');
      expect(outage.broken_feature_count).toBe(0);

      proxy.setOutage(false);
      await page.reload();
      await expect(page.getByLabel('장소 정보 사용 불가').first()).toBeVisible();
      await expect(page.getByText('정보 사용 불가 1곳').first()).toBeVisible();
      expect(proxy.batchRequests.length).toBeGreaterThan(outageBatchCount);
      const recovered = await readTrip(page, tripId);
      const recoveredPois = poisByFeatureId(recovered);
      expect(recoveredPois.get(realFeature.feature_id)?.feature_resolution_state).toBe('found');
      expect(recoveredPois.get(opaqueFeatureId)?.feature_resolution_state).toBe('missing');
      expect(recovered.broken_feature_count).toBe(1);
    } finally {
      proxy.setOutage(false);
      try {
        if (tripId) await cleanupTrip(page, tripId);
      } finally {
        await proxy.close();
      }
    }
  });
});
