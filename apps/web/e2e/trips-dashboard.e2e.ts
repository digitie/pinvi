import { expect, test, type Page } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const poiId = '44444444-4444-4444-8444-444444444444';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function trip(title = '서울 주말 산책', overrides: Record<string, unknown> = {}) {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title,
    description: null,
    region_hint: '서울',
    primary_region_code: '11',
    primary_region_source: 'manual',
    start_date: '2099-06-20',
    end_date: '2099-06-21',
    visibility: 'private',
    status: 'draft',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
    ...overrides,
  };
}

async function mockTripDetail(page: Page) {
  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: trip(),
          days: [
            {
              day_index: 1,
              date: '2026-06-20',
              title: '1일차',
              pois: [
                {
                  poi_id: poiId,
                  feature_id: 'feat-gyeongbokgung',
                  sort_order: '0100',
                  title: '경복궁',
                  feature: { coord: { lon: 126.977, lat: 37.5796 }, category: '국가유산' },
                  marker_color: 'P-03',
                  marker_icon: 'monument',
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
          companions: [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
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

test('/trips는 meta null 목록 응답과 전체 지도 POI를 렌더링한다', async ({ page }) => {
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: [trip()],
        meta: {
          cursor: null,
          has_more: false,
          total: null,
          page: null,
          limit: 50,
          version: null,
        },
      }),
    });
  });
  await mockTripDetail(page);

  await page.goto('/trips');

  await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();
  await expect(page.getByTestId('trip-list')).toContainText('서울 주말 산책');
  await expect(page.getByTestId('trip-map')).toBeVisible();
  await expectTripMapSurface(page);
  await expect(
    page.locator(`[data-testid="trip-map-marker-style"][data-poi-id="${poiId}"]`),
  ).toHaveText('경복궁');
});

test('/trips는 예정 여행을 날짜 오름차순으로 보여주고 지난 여행은 탭으로 분리한다', async ({
  page,
}) => {
  const trips = [
    trip('제주 여름휴가', {
      trip_id: '11111111-1111-4111-8111-111111111113',
      start_date: '2099-08-01',
      end_date: '2099-08-03',
      status: 'planned',
    }),
    trip('부산 1박 2일', {
      trip_id: '11111111-1111-4111-8111-111111111114',
      start_date: '2099-07-01',
      end_date: '2099-07-02',
      status: 'planned',
    }),
    trip('속초 겨울 여행', {
      trip_id: '11111111-1111-4111-8111-111111111115',
      start_date: '2000-01-01',
      end_date: '2000-01-03',
      status: 'completed',
    }),
    trip('강릉 당일치기', {
      trip_id: '11111111-1111-4111-8111-111111111116',
      start_date: '2099-07-01',
      end_date: '2099-07-01',
      status: 'planned',
    }),
  ];

  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: trips }),
    });
  });
  await mockTripDetail(page);

  await page.goto('/trips');

  await expect(page.getByRole('tab', { name: '예정' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.getByTestId('trip-list').locator('h2')).toHaveText([
    '강릉 당일치기',
    '부산 1박 2일',
    '제주 여름휴가',
  ]);
  await expect(page.getByTestId('trip-list')).not.toContainText('속초 겨울 여행');

  await page.getByRole('tab', { name: '지난 여행' }).click();
  await expect(page.getByTestId('trip-list').locator('h2')).toHaveText(['속초 겨울 여행']);
});

test.describe('/trips Samsung Internet 모바일 레이아웃', () => {
  test.use({
    viewport: { width: 1180, height: 915 },
    deviceScaleFactor: 2.625,
    isMobile: true,
    hasTouch: true,
    userAgent:
      'Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S921N) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36',
  });

  test('큰 layout viewport에서도 지도 없이 여행 목록을 먼저 렌더링하고 관리 폼은 필요할 때 연다', async ({
    page,
  }) => {
    await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
      if (!isFetch(request.resourceType())) return route.continue();
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [trip()] }),
      });
    });
    await mockTripDetail(page);

    await page.goto('/trips');

    await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();
    await expect(page.getByTestId('trip-list')).toBeVisible();
    await expect(page.getByTestId('trip-list')).toContainText('서울 주말 산책');
    await expect(page.getByTestId('trip-map')).toBeHidden();
    await expect(page.getByTestId('trip-create-title')).toBeHidden();

    await page.getByRole('button', { name: '관리 열기' }).click();
    await expect(page.getByTestId('trip-create-title')).toBeVisible();
  });
});

test('/trips에서 날짜가 없는 초안 여행을 저장할 수 있다', async ({ page }) => {
  let created = false;

  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'POST') {
      const body = request.postDataJSON();
      expect(body).toMatchObject({
        title: '날짜 미정 초안',
        start_date: null,
        end_date: null,
        visibility: 'private',
      });
      created = true;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          data: trip('날짜 미정 초안', { start_date: null, end_date: null }),
        }),
      });
      return;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.goto('/trips');
  await page.getByTestId('trip-create-title').fill('날짜 미정 초안');
  await page.getByTestId('trip-create-submit').click();

  await expect(page.getByText('초안 여행을 저장했습니다.')).toBeVisible();
  await expect(page.getByTestId('trip-list')).toContainText('날짜 미정 초안');
  expect(created).toBe(true);
});
