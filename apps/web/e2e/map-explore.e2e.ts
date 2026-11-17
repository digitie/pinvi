import { expect, test } from './fixtures';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

// 탐색 지도(`/map`) — VWorld 키 유무와 무관하게 셸 + 컨트롤이 렌더된다.
test('탐색 지도가 검색·내 위치 컨트롤과 함께 렌더링된다', async ({ page }) => {
  // 키가 있으면 onLoad 에서 in-bounds 를 부르므로 mock(없으면 호출 안 됨 — 둘 다 허용).
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          items: [],
          clusters: [],
          cluster_unit: 'individual',
          zoom: 12,
          bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
        },
      }),
    });
  });

  await page.goto('/map');

  await expect(page.getByRole('heading', { name: '탐색 지도' })).toBeVisible();
  await expect(page.getByTestId('map-search')).toBeVisible();
  await expect(page.getByTestId('map-my-location')).toBeVisible();
  await expect(page.getByTestId('feature-map')).toBeVisible();

  // VWorld 키 미설정 시 fallback, 설정 시 canvas — 둘 중 하나는 보여야 한다.
  const fallback = page.getByTestId('vworld-map-fallback');
  const canvas = page.locator('.maplibregl-canvas').first();
  await expect(fallback.or(canvas)).toBeVisible();
});

// 2026-11-02 prod e2e — 데스크톱 탐색 지도가 테두리 상자를 다 채우지 못하고 360px(min-h)에서 멈춰
// 아래 절반 이상이 비었다. 지도(또는 키가 없을 때의 fallback)는 지도 상자 높이를 채워야 한다.
test('탐색 지도는 데스크톱에서 지도 상자 높이를 채운다', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          items: [],
          clusters: [],
          cluster_unit: 'individual',
          zoom: 12,
          bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
        },
      }),
    });
  });

  await page.goto('/map');

  // 테두리 지도 상자 = `feature-map`의 첫 자식(검색·지도 영역).
  const frame = page.getByTestId('feature-map').locator(':scope > div').first();
  const surface = page
    .getByTestId('vworld-map-fallback')
    .or(page.getByTestId('vworld-map-container'))
    .first();
  await expect(surface).toBeVisible();
  const frameBox = await frame.boundingBox();
  const surfaceBox = await surface.boundingBox();
  expect(frameBox).not.toBeNull();
  expect(surfaceBox).not.toBeNull();
  expect(frameBox!.height).toBeGreaterThan(450);
  expect(Math.abs(surfaceBox!.height - frameBox!.height)).toBeLessThanOrEqual(4);
});

/* ───────────── 전체 화면 지도 + 여행 지도와 같은 장소 마커 (소유자 요청 2026-11-17) ───────────── */

const BBOX = { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 };
// 기본 중심(서울시청, `DEFAULT_MAP_CENTER`)에 둔 장소 — 진입하자마자 화면 가운데에 그려진다.
const CENTER_FEATURE = {
  feature_id: 'e2e-explore-feature-1',
  kind: 'place',
  name: '서울도서관',
  coord: { lon: 126.978, lat: 37.5665 },
  category: '미술관/박물관',
  category_label: '미술관/박물관',
  marker_color: 'P-09',
  marker_icon: 'museum',
};

type Box = { x: number; y: number; width: number; height: number };
const intersects = (a: Box, b: Box) =>
  a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;

/** 탐색 지도가 부르는 API를 모두 mock한다(mock 없는 요청은 network fence 위반이다). */
async function mockExploreRoutes(
  page: import('@playwright/test').Page,
  items: (typeof CENTER_FEATURE)[] = [],
) {
  await page.route(/.*\/features\/in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: { items, clusters: [], cluster_unit: 'individual', zoom: 14, bbox: BBOX },
      }),
    });
  });
  await page.route(/.*\/weather\/markers-in-bounds(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { items: [], zoom: 14, bbox: BBOX } }),
    });
  });
  // 선택 popup의 상세·날씨 — 이 검사는 popup 자리만 보므로 일시 오류로 답한다(popup은 제목으로 degrade).
  await page.route(/.*\/features\/[^/?]+\/(detail-card|weather)(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.fallback();
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'upstream_unavailable', message: '잠시 후 다시' } }),
    });
  });
}

test('탐색 지도는 데스크톱에서 상단 바 아래 창 전체를 지도로 쓴다', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockExploreRoutes(page);
  await page.goto('/map');

  const map = page.getByTestId('feature-map');
  await expect(map).toBeVisible();
  const header = (await page.getByRole('banner').boundingBox())!;
  const box = (await map.boundingBox())!;
  // 좌우·아래 여백 없음, 위는 얇은 상단 바(≤ 56px) 바로 아래.
  expect(header.height).toBeLessThanOrEqual(56);
  expect(box.x).toBe(0);
  expect(Math.round(box.width)).toBe(1440);
  expect(Math.abs(box.y - (header.y + header.height))).toBeLessThanOrEqual(1);
  expect(Math.abs(box.y + box.height - 900)).toBeLessThanOrEqual(1);
  // 페이지 자체는 스크롤되지 않는다.
  const scroll = await page.evaluate(() => ({
    h: document.scrollingElement!.scrollHeight,
    w: document.scrollingElement!.scrollWidth,
  }));
  expect(scroll.h).toBeLessThanOrEqual(900);
  expect(scroll.w).toBeLessThanOrEqual(1440);
  // 제목은 화면에서 숨기고 읽기 도구용으로 남긴다(h1 1개).
  await expect(page.getByRole('heading', { level: 1, name: '탐색 지도' })).toHaveCount(1);
});

test('탐색 지도는 390px 모바일에서 하단 탭바 위까지 지도로 쓰고 가로 스크롤이 없다', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockExploreRoutes(page);
  await page.goto('/map');

  const map = page.getByTestId('feature-map');
  await expect(map).toBeVisible();
  const tabbar = (await page.getByRole('navigation', { name: '주요 메뉴' }).boundingBox())!;
  const box = (await map.boundingBox())!;
  // 모바일은 상단 바도 숨긴다 — 지도가 맨 위부터 탭바 위까지.
  await expect(page.getByRole('banner')).toBeHidden();
  expect(box.x).toBe(0);
  expect(box.y).toBe(0);
  expect(Math.round(box.width)).toBe(390);
  expect(Math.abs(box.y + box.height - tabbar.y)).toBeLessThanOrEqual(2);
  const scrollWidth = await page.evaluate(() => document.scrollingElement!.scrollWidth);
  expect(scrollWidth).toBeLessThanOrEqual(390);

  // 오버레이끼리 겹치지 않는다 — 왼쪽 위 스택(검색·레이어)과 오른쪽 아래 내 위치 버튼, 그리고 둘 다 지도 안.
  const stack = (await page.getByTestId('feature-map-overlay-stack').boundingBox())!;
  const layers = (await page.getByTestId('map-layer-controls').boundingBox())!;
  const myLocation = (await page.getByTestId('map-my-location').boundingBox())!;
  expect(intersects(stack, myLocation)).toBe(false);
  expect(stack.x + stack.width).toBeLessThanOrEqual(390 - 40); // 오른쪽 위 확대/축소 버튼 자리
  expect(layers.y).toBeGreaterThanOrEqual(stack.y);
  expect(myLocation.y + myLocation.height).toBeLessThanOrEqual(tabbar.y);

  // 레이어 패널은 접고 펼 수 있다(켠 레이어는 그대로).
  await page.getByTestId('map-layer-controls-toggle').click();
  await expect(page.getByTestId('map-layer-controls')).toHaveAttribute('data-collapsed', 'true');
  await expect(page.getByTestId('geometry-route-toggle')).toHaveCount(0);
  await page.getByTestId('map-layer-controls-toggle').click();
  await expect(page.getByTestId('geometry-route-toggle')).toBeVisible();
});

test('탐색 지도 장소 마커는 여행 지도와 같은 원형 + 상자 없는 이름 라벨이다', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockExploreRoutes(page, [CENTER_FEATURE]);
  await page.goto('/map');
  const legend = page.locator(
    `[data-testid="feature-map-marker-style"][data-feature-id="${CENTER_FEATURE.feature_id}"]`,
  );

  test.skip(process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1', 'VWorld canvas 검증 환경에서 실행');
  await expect(legend).toHaveAttribute('data-marker-size', '22');
  await expect(legend).toHaveAttribute('data-marker-label', 'true');
  await expect(legend).toHaveAttribute('data-marker-icon', 'museum');
  const marker = page.locator('.maplibregl-marker.explore-map-marker').first();
  await expect(marker).toBeVisible({ timeout: 20_000 });
  // 마커 루트 계약(live e2e `featureMarkerButtons`)은 그대로다.
  await expect(marker).toHaveAttribute('role', 'button');
  await expect(marker).toHaveAttribute('aria-label', CENTER_FEATURE.name);
  await expect(marker).toHaveAttribute(
    'data-interaction-id',
    `feature:${CENTER_FEATURE.feature_id}`,
  );
  const dot = marker.getByTestId('circle-place-marker-dot');
  const dotBox = (await dot.boundingBox())!;
  expect(Math.round(dotBox.width)).toBe(22);
  expect(Math.round(dotBox.height)).toBe(22);
  expect(await dot.evaluate((el) => getComputedStyle(el).borderRadius)).not.toBe('0px');
  const label = marker.getByTestId('circle-place-marker-label');
  await expect(label).toContainText(CENTER_FEATURE.name);
  const labelStyle = await label.evaluate((el) => {
    const style = getComputedStyle(el);
    return { bg: style.backgroundColor, shadow: style.boxShadow, border: style.borderTopWidth };
  });
  expect(labelStyle).toEqual({ bg: 'rgba(0, 0, 0, 0)', shadow: 'none', border: '0px' });
  expect((await label.boundingBox())!.x).toBeGreaterThan(dotBox.x + dotBox.width - 1);
  // 장소별 날씨는 받지 않으므로 날씨 아이콘은 없다.
  await expect(marker.getByTestId('place-weather-glyph')).toHaveCount(0);
  // 라벨을 눌러도 장소가 선택되고 데스크톱 popup이 뜬다.
  await label.click();
  await expect(legend).toHaveAttribute('data-marker-selected', 'true');
  await expect(page.getByTestId('feature-map-popup')).toBeVisible();
});

test('탐색 지도 선택 popup은 왼쪽 위 레이어 체크박스를 덮지 않는다', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockExploreRoutes(page, [CENTER_FEATURE]);
  await page.goto('/map');

  test.skip(process.env.PINVI_E2E_EXPECT_VWORLD_CANVAS !== '1', 'VWorld canvas 검증 환경에서 실행');
  const marker = page.locator('.maplibregl-marker.explore-map-marker').first();
  await expect(marker).toBeVisible({ timeout: 20_000 });
  const layers = page.getByTestId('map-layer-controls');
  const layersBox = (await layers.boundingBox())!;
  const dot = marker.getByTestId('circle-place-marker-dot');

  // 장소를 레이어 패널 바로 아래로 옮긴다 — 그 위로 자라는 popup은 패널을 덮게 된다.
  const dotBox = (await dot.boundingBox())!;
  const target = { x: layersBox.x + 120, y: layersBox.y + layersBox.height + 24 };
  await page.evaluate(
    ({ dx, dy }) => {
      const element = document.querySelector('.maplibregl-map');
      type Fiber = {
        memoizedProps?: {
          value?: { getSnapshot?: () => { map?: { panBy: (o: [number, number], a: object) => void } } };
        };
        return?: Fiber;
      };
      const record = element as unknown as Record<string, unknown>;
      const key = Object.keys(record).find((name) => name.startsWith('__reactFiber'));
      let fiber = key ? (record[key] as Fiber | undefined) : undefined;
      while (fiber) {
        const map = fiber.memoizedProps?.value?.getSnapshot?.()?.map;
        if (map) {
          map.panBy([dx, dy], { animate: false });
          return;
        }
        fiber = fiber.return;
      }
      throw new Error('map instance not found');
    },
    {
      dx: dotBox.x + dotBox.width / 2 - target.x,
      dy: dotBox.y + dotBox.height / 2 - target.y,
    },
  );
  await expect
    .poll(async () => {
      const b = (await dot.boundingBox())!;
      return Math.round(b.y + b.height / 2 - target.y);
    })
    .toBe(0);

  await dot.click();
  const popup = page.locator('.maplibregl-popup');
  await expect(popup).toBeVisible();
  // popup이 패널과 겹치지 않을 때까지 지도가 비켜 선다(구글 지도 InfoWindow autoPan과 같은 동작).
  await expect
    .poll(async () => intersects((await popup.boundingBox())!, (await layers.boundingBox())!), {
      timeout: 5_000,
    })
    .toBe(false);
  // 체크박스가 맨 위 요소다 — 무엇에도 가리지 않고 눌린다(force 없이).
  const toggle = page.getByTestId('geometry-route-toggle');
  const covered = await toggle.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !(top && (top === el || el.closest('label')?.contains(top)));
  });
  expect(covered).toBe(false);
  const before = await toggle.isChecked();
  await toggle.click();
  await expect(toggle).toBeChecked({ checked: !before });
  // popup은 그대로 열려 있다(지도만 옮겼다).
  await expect(page.getByTestId('feature-map-popup')).toBeVisible();
});
