import { expect, test, type Page } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const poiId = '44444444-4444-4444-8444-444444444444';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

function tripResponse(title: string, version: number) {
  return {
    trip_id: tripId,
    owner_user_id: userId,
    title,
    description: null,
    region_hint: '서울',
    primary_region_code: null,
    primary_region_source: null,
    start_date: null,
    end_date: null,
    visibility: 'private',
    status: 'draft',
    version,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

function poiResponse(note: string | null, version: number) {
  return {
    poi_id: poiId,
    feature_id: 'feat-1',
    sort_order: '0100',
    title: '경복궁',
    feature: { coord: { lon: 126.977, lat: 37.5796 } },
    marker_color: 'P-09',
    marker_icon: 'museum',
    is_broken: false,
    user_note: note,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  };
}

function tripView(title: string, tripVersion: number, note: string | null, poiVersion: number) {
  return {
    trip: tripResponse(title, tripVersion),
    days: [{ day_index: 1, date: null, title: '1일차', pois: [poiResponse(note, poiVersion)] }],
    companions: [],
    share_links: [],
    broken_feature_count: 0,
  };
}

async function commonRoutes(page: Page) {
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
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/attachments.*$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });
}

function conflictBody() {
  return {
    error: {
      code: 'VERSION_CONFLICT',
      message: '동시 편집 충돌 — 다시 불러와 주세요.',
    },
  };
}

test('여행 정보 409 충돌에서 내 값 전체를 최신 version으로 다시 저장한다', async ({ page }) => {
  let patchCount = 0;
  let serverChanged = false;
  let clientWon = false;
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (request.method() === 'PATCH') {
      patchCount += 1;
      if (patchCount === 1) {
        expect(request.headers()['if-match']).toBe('1');
        serverChanged = true;
        await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify(conflictBody()) });
        return;
      }
      expect(request.headers()['if-match']).toBe('2');
      expect(await request.postDataJSON()).toMatchObject({ title: '내 제목' });
      clientWon = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: tripResponse('내 제목', 3) }),
      });
      return;
    }
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: clientWon
          ? tripView('내 제목', 3, null, 1)
          : serverChanged
            ? tripView('서버 제목', 2, null, 1)
            : tripView('원래 제목', 1, null, 1),
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByRole('button', { name: '편집', exact: true }).click();
  await page.getByLabel('제목').fill('내 제목');
  await page.getByTestId('trip-edit-save').click();

  const dialog = page.getByTestId('conflict-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('서버 제목');
  await expect(dialog).toContainText('내 제목');

  await page.getByTestId('conflict-use-mine').click();

  await expect(page.getByRole('heading', { name: '내 제목' })).toBeVisible();
  expect(patchCount).toBe(2);
});

test('POI 409 충돌에서 내 메모를 최신 version으로 다시 저장한다', async ({ page }) => {
  let patchCount = 0;
  let serverChanged = false;
  let clientWon = false;
  await commonRoutes(page);

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/pois\/[0-9a-f-]{36}$/, async (route, request) => {
    if (request.method() !== 'PATCH') return route.continue();
    patchCount += 1;
    if (patchCount === 1) {
      expect(request.headers()['if-match']).toBe('1');
      serverChanged = true;
      await route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify(conflictBody()) });
      return;
    }
    expect(request.headers()['if-match']).toBe('2');
    expect(await request.postDataJSON()).toMatchObject({ user_note: '내 메모' });
    clientWon = true;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { ...poiResponse('내 메모', 3), attachment_id: poiId, trip_id: tripId, day_index: 1 } }),
    });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: clientWon
          ? tripView('POI 충돌 여행', 1, '내 메모', 3)
          : serverChanged
            ? tripView('POI 충돌 여행', 1, '서버 메모', 2)
            : tripView('POI 충돌 여행', 1, null, 1),
      }),
    });
  });

  await page.goto(`/trips/${tripId}`);
  await page.getByRole('button', { name: '마커 편집' }).click();
  const editor = page.getByTestId('poi-editor');
  await editor.getByLabel('메모').fill('내 메모');
  await editor.getByRole('button', { name: '저장' }).click();

  const dialog = page.getByTestId('conflict-dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('서버 메모');
  await expect(dialog).toContainText('내 메모');

  await page.getByTestId('conflict-use-mine').click();

  await expect(page.getByTestId('trip-poi-list')).toContainText('내 메모');
  expect(patchCount).toBe(2);
});
