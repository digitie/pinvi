import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const poiId = '44444444-4444-4444-8444-444444444444';
const companionId = '55555555-5555-4555-8555-555555555555';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function trip() {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title: '변경 테스트 여행',
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

function poi() {
  return {
    poi_id: poiId,
    feature_id: 'feat-1',
    sort_order: '0100',
    title: '경복궁',
    feature: { coord: { lon: 126.977, lat: 37.5796 } },
    marker_color: 'P-09',
    marker_icon: 'museum',
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

function poiMutationResponse() {
  const item = poi();
  return {
    attachment_id: item.poi_id,
    trip_id: tripId,
    day_index: 1,
    sort_order: item.sort_order,
    feature_id: item.feature_id,
    feature_link_broken_at: item.feature_link_broken_at,
    feature_snapshot: item.feature,
    custom_marker_color: item.marker_color,
    custom_marker_icon: item.marker_icon,
    planned_arrival_at: item.planned_arrival_at,
    planned_departure_at: item.planned_departure_at,
    user_note: item.user_note,
    budget_amount: item.budget_amount,
    actual_amount: item.actual_amount,
    currency: item.currency,
    user_url: item.user_url,
    rise_set: item.rise_set,
    version: 2,
    created_at: item.created_at,
    updated_at: item.updated_at,
  };
}

function day(pois: ReturnType<typeof poi>[]) {
  return { day_index: 1, date: null, title: '1일차', pois };
}

function companion() {
  return {
    companion_id: companionId,
    trip_id: tripId,
    user_id: null,
    invited_email: 'friend@example.com',
    invited_nickname: null,
    role: 'editor',
    invited_at: '2026-06-01T09:00:00+09:00',
    joined_at: null,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

async function commonRoutes(page: import('@playwright/test').Page) {
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
}

test('동반자를 초대하면 목록에 나타난다', async ({ page }) => {
  let invited = false;
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/members$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    invited = true;
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: companion() }) });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: trip(),
          days: [day([poi()])],
          companions: invited ? [companion()] : [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByRole('heading', { name: '변경 테스트 여행' })).toBeVisible();

  await page.getByRole('tab', { name: /동행/ }).click();
  await page.getByLabel('이메일').fill('friend@example.com');
  await page.getByRole('button', { name: '초대' }).click();

  await expect(page.getByTestId('companion-list')).toContainText('friend@example.com');
});

test('POI를 삭제하면 장소 목록에서 제거된다', async ({ page }) => {
  let deleted = false;
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/pois\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'DELETE') {
      deleted = true;
      await route.fulfill({ status: 204, body: '' });
      return;
    }
    await route.continue();
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: trip(),
          days: [day(deleted ? [] : [poi()])],
          companions: [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await expect(page.getByTestId('trip-poi-list')).toContainText('경복궁');

  await page.getByRole('button', { name: '장소 삭제' }).click();

  await expect(page.getByTestId('trip-poi-list')).toHaveCount(0);
  await expect(page.getByText('등록된 장소가 없습니다')).toHaveCount(0);
});

test('POI 마커 편집기를 열고 저장하면 닫힌다', async ({ page }) => {
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/pois\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'PATCH') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: poiMutationResponse() }),
      });
      return;
    }
    await route.continue();
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          trip: trip(),
          days: [day([poi()])],
          companions: [],
          share_links: [],
          broken_feature_count: 0,
        },
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByRole('button', { name: '마커 편집' }).click();

  const editor = page.getByTestId('poi-editor');
  await expect(editor).toBeVisible();

  // FormField/FormTextArea로 label↔input이 연결됐는지(접근성) 확인.
  await expect(editor.getByLabel('메모')).toBeVisible();
  await expect(editor.getByLabel('링크')).toBeVisible();
  await expect(editor.getByLabel('예산')).toBeVisible();

  await editor.getByRole('button', { name: '저장' }).click();
  await expect(editor).toBeHidden();
});
