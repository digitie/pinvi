import { expect, test, type Page } from './fixtures';

/**
 * 주유소·교통 돌발 마커와 상세 — kor-travel-transport 유가 지도와 같은 모양(소유자 요청 2026-11-27).
 *
 * - 주유소 마커: 상표 로고 칩 + 오른쪽 흰 가격 라벨("휘 1,650"), 판매하지 않는 유종은 라벨에도 없다.
 * - 교통 돌발 마커: 24px 원 배지.
 * - 화면 예산(22,000px²당 1곳)을 넘으면 묶음 거품, 안이면 펼친다.
 * - 상세: 판매 중인 유종만, `원/L`, 상표 로고.
 *
 * 실제 MapLibre canvas가 있어야 마커가 붙는다(`test:e2e:map-canvas`). `PINVI_E2E_SHOT_DIR`을 주면 화면을 남긴다.
 */

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);
const BBOX = { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 };
const CENTER = { lon: 126.978, lat: 37.5665 };
const FRESHNESS = {
  source_collected_at: '2026-10-23T09:00:00+09:00',
  loaded_at: '2026-10-23T09:05:00+09:00',
  age_seconds: 600,
  max_age_seconds: 172800,
  stale: false,
};
const BRANDS = [
  ['SKE', 'SK에너지'],
  ['GSC', 'GS칼텍스'],
  ['HDO', 'HD현대오일뱅크'],
  ['SOL', 'S-OIL'],
  ['RTO', '알뜰주유소'],
  ['ETC', '자가상표'],
] as const;

function station(index: number, lon: number, lat: number) {
  const [code, name] = BRANDS[index % BRANDS.length]!;
  const at = '2026-10-23T09:00:00+09:00';
  return {
    layer: 'fuel_station',
    feature_id: `f_e2e_fuel_${index}`,
    category: '06020000',
    marker_icon: 'fuel',
    marker_color: 'P-08',
    coord: { lon, lat },
    name: `${name.replace(/\s.*/, '')} 테스트${index}주유소`,
    address: { road: `서울 중구 세종대로 ${index + 1}`, jibun: null },
    brand_code: code,
    brand_name: name,
    phone: '02-000-0000',
    is_self: index % 2 === 0,
    is_24h: index % 3 === 0,
    has_carwash: true,
    has_cvs: index % 2 === 1,
    has_maintenance: false,
    lpg_available: false,
    source_last_seen_at: at,
    prices: [
      {
        product_key: 'gasoline',
        product_code: 'B027',
        product_name: '휘발유',
        price: 1650 + index,
        collected_at: at,
      },
      // 경유를 팔지 않는 주유소(첫 곳) — 라벨·상세 어디에도 없어야 한다.
      {
        product_key: 'diesel',
        product_code: 'D047',
        product_name: '경유',
        price: index === 0 ? null : 1540 + index,
        collected_at: at,
      },
      {
        product_key: 'lpg',
        product_code: 'K015',
        product_name: 'LPG',
        price: index === 0 ? 1100 : 0,
        collected_at: at,
      },
    ],
  };
}

const INCIDENT = {
  layer: 'highway_incident',
  feature_id: 'f_e2e_incident',
  category: '99000000',
  marker_icon: 'roadblock',
  marker_color: 'P-13',
  coord: { lon: CENTER.lon + 0.012, lat: CENTER.lat - 0.008 },
  title: '세종대로 사고',
  message: '2차로 사고 처리 중',
  incident_type: '사고',
  process_status: '처리중',
  route_no: '0010',
  route_name: '경부선',
  direction: '서울',
  point_name: '기흥IC',
  congestion_length: 1.5,
  occurred_at: '2026-10-23T08:40:00+09:00',
};

const SPARSE = [
  station(0, CENTER.lon, CENTER.lat),
  station(1, CENTER.lon - 0.014, CENTER.lat + 0.008),
  station(2, CENTER.lon + 0.016, CENTER.lat + 0.01),
];
// 시청 주변 0.04° 격자에 64곳 — 375px 화면 예산(11곳)과 데스크톱 예산(58곳)을 모두 넘는다.
const DENSE = Array.from({ length: 64 }, (_, i) =>
  station(i, CENTER.lon - 0.04 + (i % 8) * 0.0114, CENTER.lat - 0.025 + Math.floor(i / 8) * 0.007),
);

async function mockRoutes(page: Page, stations: ReturnType<typeof station>[]) {
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: { items: [], clusters: [], cluster_unit: 'individual', zoom: 12, bbox: BBOX },
      }),
    });
  });
  await page.route(/.*\/weather\/markers-in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { items: [], zoom: 12, bbox: BBOX } }),
    });
  });
  await page.route(/.*\/transport\/status$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          enabled: true,
          layers: [
            { layer: 'fuel_station', available: true, reason: null, freshness: FRESHNESS },
            { layer: 'highway_incident', available: true, reason: null, freshness: FRESHNESS },
          ],
        },
      }),
    });
  });
  await page.route(/.*\/transport\/markers-in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    const layers = (new URL(request.url()).searchParams.get('layers') ?? '')
      .split(',')
      .filter(Boolean);
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          bbox: BBOX,
          zoom: 12,
          layers: layers.map((layer) => ({
            layer,
            status: 'ok',
            reason: null,
            freshness: FRESHNESS,
            truncated: false,
            items:
              layer === 'fuel_station' ? stations : layer === 'highway_incident' ? [INCIDENT] : [],
          })),
        },
      }),
    });
  });
  await page.route(/.*\/transport\/fuel-stations\/[^/?]+(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    const id = new URL(request.url()).pathname.split('/').pop();
    const item = stations.find((s) => s.feature_id === id) ?? stations[0];
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { item, freshness: FRESHNESS } }),
    });
  });
  await page.route(/.*\/transport\/highway-incidents\/[^/?]+(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { item: INCIDENT, freshness: FRESHNESS } }),
    });
  });
}

async function shot(page: Page, name: string) {
  const dir = process.env.PINVI_E2E_SHOT_DIR;
  if (dir) await page.screenshot({ path: `${dir}/${name}.png` });
}

const fuelMarker = (page: Page, id: string) =>
  page.locator(`.maplibregl-marker[data-interaction-id="transport:fuel_station:${id}"]`);

for (const viewport of [
  { name: '375', width: 375, height: 812 },
  { name: 'desktop', width: 1440, height: 900 },
]) {
  test(`주유소 마커는 transport식 로고 칩 + 가격 라벨이고 상세는 판매 유종만 (${viewport.name})`, async ({
    page,
  }) => {
    test.skip(
      process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1',
      'VWorld canvas 검증 환경에서 실행',
    );
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockRoutes(page, SPARSE);
    await page.goto('/map');
    await page.getByTestId('transport-layer-toggle-fuel_station').check();
    await page.getByTestId('transport-layer-toggle-highway_incident').check();

    const first = fuelMarker(page, SPARSE[0]!.feature_id);
    await expect(first).toBeVisible({ timeout: 20_000 });
    // 예산 안 — 묶지 않고 세 곳 모두 펼친다.
    await expect(page.getByTestId('fuel-station-marker')).toHaveCount(3);
    const chip = first.getByTestId('fuel-station-marker');
    const box = (await chip.boundingBox())!;
    // 로고 40×24 + 안쪽 여백 2px + 테두리 1px — 예전 핀 마커보다 낮고, transport 칩과 같다.
    expect(Math.round(box.width)).toBe(46);
    expect(Math.round(box.height)).toBe(30);
    const label = first.getByTestId('fuel-station-marker-price');
    // 첫 곳은 경유를 팔지 않는다 — 라벨에 경유 줄이 없다(LPG는 판다).
    await expect(label).toHaveText('휘 1,650\nLPG 1,100');
    await expect(first).toHaveAttribute('aria-label', /휘발유 1,650원, LPG 1,100원 상세 보기$/);
    // 교통 돌발은 24px 원 배지.
    const incident = page.locator(
      '.maplibregl-marker[data-interaction-id="transport:highway_incident:f_e2e_incident"]',
    );
    const dot = incident.getByTestId('circle-place-marker-dot');
    await expect(dot).toBeVisible();
    expect(Math.round((await dot.boundingBox())!.width)).toBe(24);
    await shot(page, `fuel-markers-sparse-${viewport.name}`);

    await chip.click();
    const prices = page.getByTestId('transport-fuel-prices');
    await expect(prices).toBeVisible();
    await expect(prices.getByTestId('transport-fuel-price')).toHaveCount(2);
    await expect(prices).toContainText('1,650원/L');
    await expect(prices).not.toContainText('경유');
    await expect(page.getByTestId('fuel-brand')).toContainText('SK에너지');
    // 좁은 화면에서도 가로 넘침이 없다.
    const overflow = await page
      .getByTestId('transport-detail')
      .evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await shot(page, `fuel-detail-${viewport.name}`);
    await page.keyboard.press('Escape');

    await dot.click();
    await expect(page.getByTestId('transport-incident-route')).toHaveText('0010 · 경부선');
    await expect(page.getByTestId('transport-incident-status')).toHaveText('사고 · 처리중');
    await shot(page, `incident-detail-${viewport.name}`);
  });

  test(`주유소가 화면 예산보다 많으면 묶는다 (${viewport.name})`, async ({ page }) => {
    test.skip(
      process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1',
      'VWorld canvas 검증 환경에서 실행',
    );
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockRoutes(page, DENSE);
    await page.goto('/map');
    await page.getByTestId('transport-layer-toggle-fuel_station').check();
    await expect(
      page.getByTestId('transport-marker-legend').getByTestId('transport-marker'),
    ).toHaveCount(64);
    // 64곳은 두 화면 예산을 모두 넘는다 — 일부는 묶음 거품이 되고 펼친 마커는 64곳보다 적다.
    await expect
      .poll(async () => page.getByTestId('fuel-station-marker').count(), { timeout: 20_000 })
      .toBeLessThan(64);
    await expect.poll(async () => page.locator('.maplibregl-marker').count()).toBeGreaterThan(0);
    await shot(page, `fuel-markers-dense-${viewport.name}`);
  });
}
