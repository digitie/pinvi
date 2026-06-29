import { expect, test } from '@playwright/test';
import type {
  AdminOperationImpact,
  AdminOperationResult,
  AdminPoiDetail,
  AdminPoiSummary,
  AdminTripSummary,
} from '@pinvi/schemas';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const poiId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const createdPoiId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const tripId = '88888888-8888-4888-8888-888888888888';
const ownerUserId = '99999999-9999-4999-8999-999999999999';
const addedByUserId = '66666666-6666-4666-8666-666666666666';

const poiSummary: AdminPoiSummary = {
  attachment_id: poiId,
  trip_id: tripId,
  trip_title: '부산 가족 여행',
  owner_user_id: ownerUserId,
  owner_email_masked: 'o***@example.com',
  day_index: 1,
  sort_order: 'a0',
  feature_id: 'place-haeundae',
  feature_label: '해운대 해수욕장',
  feature_link_broken_at: null,
  version: 1,
  created_at: '2026-06-06T10:00:00+09:00',
  updated_at: '2026-06-06T11:00:00+09:00',
};

const tripSummary: AdminTripSummary = {
  trip_id: tripId,
  owner_user_id: ownerUserId,
  owner_email_masked: 'o***@example.com',
  title: '부산 가족 여행',
  region_hint: '부산',
  primary_region_code: '26',
  primary_region_source: 'manual',
  start_date: '2026-07-01',
  end_date: '2026-07-03',
  visibility: 'private',
  status: 'planned',
  version: 1,
  day_count: 2,
  poi_count: 1,
  companion_count: 0,
  share_link_count: 0,
  created_at: '2026-06-06T10:00:00+09:00',
  updated_at: '2026-06-06T11:00:00+09:00',
};

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
});

test('Admin POI 목록이 검색어와 연결 필터를 API에 전달한다', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/pois',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [poiSummary],
            total: 1,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.goto('/admin/pois');
  await expect(page.getByRole('heading', { name: 'POI' })).toBeVisible();
  await expect(page.getByText('해운대 해수욕장')).toBeVisible();

  await page.getByTestId('admin-pois-search').fill('haeundae');
  await page.getByTestId('admin-pois-search-submit').click();
  await expect.poll(() => requests.some((url) => url.includes('q=haeundae'))).toBe(true);

  await page.getByTestId('admin-pois-broken-filter').selectOption('false');
  await expect
    .poll(() =>
      requests.some(
        (url) => url.includes('q=haeundae') && url.includes('has_broken_link=false'),
      ),
    )
    .toBe(true);

  await page.getByTestId('admin-pois-broken-filter').selectOption('true');
  await expect
    .poll(() =>
      requests.some(
        (url) => url.includes('q=haeundae') && url.includes('has_broken_link=true'),
      ),
    )
    .toBe(true);

  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin POI 목록에서 POI를 직접 생성한다', async ({ page }) => {
  let createBody: Record<string, unknown> | null = null;
  const createdPoi: AdminPoiDetail = {
    attachment_id: createdPoiId,
    trip_id: tripId,
    trip_title: '부산 가족 여행',
    owner_user_id: ownerUserId,
    owner_email_masked: 'o***@example.com',
    day_index: 2,
    sort_order: 'a0',
    feature_id: 'place-gangneung',
    feature_label: '강릉 커피거리',
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-06-06T12:00:00+09:00',
    updated_at: '2026-06-06T12:00:00+09:00',
    added_by_user_id: adminUser.user_id,
    added_by_email_masked: 'a***@example.com',
    feature_snapshot: {
      name: '강릉 커피거리',
      coord: { lon: 128.95, lat: 37.77 },
      address_label: '강원 강릉시',
    },
    custom_marker_color: 'P-08',
    custom_marker_icon: 'coffee',
    planned_arrival_at: '2026-07-02T10:00:00+09:00',
    planned_departure_at: '2026-07-02T11:00:00+09:00',
    user_note: '운영자 대행 등록',
    budget_amount: '15000.00',
    actual_amount: null,
    currency: 'KRW',
    user_url: 'https://example.com/gangneung',
    recent_audit: [
      {
        log_id: 40,
        actor_user_id: adminUser.user_id,
        action: 'poi.create',
        resource_type: 'poi',
        resource_id: createdPoiId,
        access_reason: '고객센터 요청 대행',
        target_pii_fields: null,
        prev_hash: '0'.repeat(64),
        content_hash: '2'.repeat(64),
        occurred_at: '2026-06-06T12:00:00+09:00',
      },
    ],
  };

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/trips',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [tripSummary],
            total: 1,
            page: 1,
            limit: 8,
          },
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/pois',
    async (route) => {
      if (route.request().method() === 'POST') {
        createBody = route.request().postDataJSON() as Record<string, unknown>;
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ data: createdPoi }),
        });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [],
            total: 0,
            page: 1,
            limit: 50,
          },
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${createdPoiId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: createdPoi }),
      });
    },
  );

  await page.goto('/admin/pois');
  await page.getByTestId('admin-poi-create-open').click();
  await expect(page.getByTestId('admin-poi-create-dialog')).toBeVisible();

  await page.getByTestId('admin-poi-trip-search').fill('부산');
  await page.getByTestId('admin-poi-trip-search-submit').click();
  await page.getByTestId(`admin-poi-trip-result-${tripId}`).click();
  await expect(page.getByTestId('admin-poi-trip-selected')).toContainText(tripId);

  await page.getByTestId('admin-poi-create-day').fill('2');
  await page.getByTestId('admin-poi-create-sort').fill('a0');
  await page.getByTestId('admin-poi-create-feature-id').fill('place-gangneung');
  await page.getByTestId('admin-poi-create-name').fill('강릉 커피거리');
  await page.getByTestId('admin-poi-create-lon').fill('128.95');
  await page.getByTestId('admin-poi-create-lat').fill('37.77');
  await page.getByTestId('admin-poi-create-address').fill('강원 강릉시');
  await page.getByTestId('admin-poi-create-marker-color').fill('P-08');
  await page.getByTestId('admin-poi-create-marker-icon').fill('coffee');
  await page.getByTestId('admin-poi-create-arrival').fill('2026-07-02T10:00');
  await page.getByTestId('admin-poi-create-departure').fill('2026-07-02T11:00');
  await page.getByTestId('admin-poi-create-budget').fill('15000');
  await page.getByTestId('admin-poi-create-url').fill('https://example.com/gangneung');
  await page.getByTestId('admin-poi-create-note').fill('운영자 대행 등록');
  await page.getByTestId('admin-poi-create-reason').fill('고객센터 요청 대행');
  await page.getByTestId('admin-poi-create-submit').click();

  await expect(page).toHaveURL(new RegExp(`/admin/pois/${createdPoiId}$`));
  expect(createBody).not.toBeNull();
  const submittedBody = createBody as unknown as Record<string, unknown>;
  expect(submittedBody).toMatchObject({
    trip_id: tripId,
    day_index: 2,
    sort_order: 'a0',
    feature_id: 'place-gangneung',
    custom_marker_color: 'P-08',
    custom_marker_icon: 'coffee',
    planned_arrival_at: '2026-07-02T10:00:00+09:00',
    planned_departure_at: '2026-07-02T11:00:00+09:00',
    user_note: '운영자 대행 등록',
    budget_amount: 15000,
    currency: 'KRW',
    user_url: 'https://example.com/gangneung',
    access_reason: '고객센터 요청 대행',
  });
  expect(submittedBody.feature_snapshot).toMatchObject({
    name: '강릉 커피거리',
    coord: { lon: 128.95, lat: 37.77 },
    address_label: '강원 강릉시',
  });
});

test('Admin POI 상세가 연결 상태 변경 audit을 표시한다', async ({ page }) => {
  const requests: string[] = [];
  let patchReason: string | null = null;
  let currentPoi: AdminPoiDetail = {
    ...poiSummary,
    added_by_user_id: addedByUserId,
    added_by_email_masked: 'p***@example.com',
    feature_snapshot: {
      name: '해운대 해수욕장',
      category: 'beach',
    },
    custom_marker_color: '#3366ff',
    custom_marker_icon: 'beach',
    planned_arrival_at: '2026-07-01T11:00:00+09:00',
    planned_departure_at: '2026-07-01T13:00:00+09:00',
    user_note: '점심 전에 도착',
    budget_amount: '12000.00',
    actual_amount: '10000.00',
    currency: 'KRW',
    user_url: 'https://example.com/haeundae',
    recent_audit: [],
  };

  page.on('request', (request) => requests.push(request.url()));

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${poiId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentPoi }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${poiId}/link-status`,
    async (route) => {
      const body = route.request().postDataJSON() as {
        broken: boolean;
        access_reason: string;
      };
      patchReason = body.access_reason;
      currentPoi = {
        ...currentPoi,
        feature_link_broken_at: body.broken ? '2026-06-06T12:00:00+09:00' : null,
        version: 2,
        recent_audit: [
          {
            log_id: 30,
            actor_user_id: adminUser.user_id,
            action: 'poi.update_link_status',
            resource_type: 'poi',
            resource_id: poiId,
            access_reason: body.access_reason,
            target_pii_fields: null,
            prev_hash: '0'.repeat(64),
            content_hash: '1'.repeat(64),
            occurred_at: '2026-06-06T12:00:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentPoi }),
      });
    },
  );

  await page.goto(`/admin/pois/${poiId}`);

  await expect(page.getByRole('heading', { name: '해운대 해수욕장' })).toBeVisible();
  await expect(page.getByTestId('admin-poi-info')).toContainText('p***@example.com');
  await expect(page.getByTestId('admin-poi-snapshot')).toContainText('beach');

  await page.getByTestId('admin-poi-link-status').selectOption('broken');
  await page.getByTestId('admin-poi-link-status-save').click();
  await page.getByTestId('admin-poi-action-reason').fill('feature_id 점검 결과 끊김');
  await page.getByTestId('admin-poi-action-confirm').click();

  await expect(page.getByTestId('admin-poi-audit-list')).toContainText(
    'poi.update_link_status',
  );
  expect(patchReason).toBe('feature_id 점검 결과 끊김');
  expect(requests.some((url) => url.includes('/features/'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin POI 상세에서 POI 이동 운영 작업을 실행한다', async ({ page }) => {
  let moveBody: Record<string, unknown> | null = null;
  let currentPoi: AdminPoiDetail = {
    ...poiSummary,
    added_by_user_id: addedByUserId,
    added_by_email_masked: 'p***@example.com',
    feature_snapshot: {
      name: '해운대 해수욕장',
      category: 'beach',
    },
    custom_marker_color: 'P-08',
    custom_marker_icon: 'beach',
    planned_arrival_at: '2026-07-01T11:00:00+09:00',
    planned_departure_at: '2026-07-01T13:00:00+09:00',
    user_note: '점심 전에 도착',
    budget_amount: '12000.00',
    actual_amount: '10000.00',
    currency: 'KRW',
    user_url: 'https://example.com/haeundae',
    recent_audit: [],
  };
  const impact: AdminOperationImpact = {
    target_type: 'poi',
    target_id: poiId,
    trip_id: tripId,
    day_index: 1,
    counts: { attachments: 1, comments: 1 },
    policy_options: {
      attachment_policy: [
        { value: 'move', label: '대상 날짜로 이동', allowed: true, reason: null },
        { value: 'delete', label: '함께 삭제', allowed: true, reason: null },
        {
          value: 'orphan',
          label: 'orphan으로 유지',
          allowed: false,
          reason: 'POI 첨부와 댓글은 POI 문맥이 필요합니다.',
        },
      ],
    },
    warnings: [],
  };
  const result: AdminOperationResult = {
    target_type: 'poi',
    action: 'move',
    source_trip_id: tripId,
    target_trip_id: tripId,
    target_id: poiId,
    day_index: 2,
    affected: { pois: 1, attachments: 1, comments: 1 },
  };

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${poiId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: currentPoi }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/trips',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: { items: [tripSummary], total: 1, page: 1, limit: 8 },
        }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${poiId}/operation-impact`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: impact }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/pois/${poiId}/move`,
    async (route) => {
      moveBody = route.request().postDataJSON() as Record<string, unknown>;
      currentPoi = {
        ...currentPoi,
        day_index: 2,
        recent_audit: [
          {
            log_id: 60,
            actor_user_id: adminUser.user_id,
            action: 'poi.move',
            resource_type: 'poi',
            resource_id: poiId,
            access_reason: 'POI 일정 조정',
            target_pii_fields: null,
            prev_hash: '0'.repeat(64),
            content_hash: '4'.repeat(64),
            occurred_at: '2026-06-06T13:00:00+09:00',
          },
        ],
      };
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: result }),
      });
    },
  );

  await page.goto(`/admin/pois/${poiId}`);
  await page.getByTestId('admin-poi-move-open').click();
  await expect(page.getByTestId('admin-poi-operation-dialog')).toBeVisible();
  await expect(page.getByTestId('admin-poi-operation-dialog')).toContainText('orphan');

  await page.getByTestId('admin-poi-operation-target-search').fill('부산');
  await page.getByTestId('admin-poi-operation-target-trip').selectOption(tripId);
  await page.getByTestId('admin-poi-operation-target-day').fill('2');
  await page.getByTestId('admin-poi-operation-policy').selectOption('move');
  await page.getByTestId('admin-poi-operation-reason').fill('POI 일정 조정');
  await page.getByTestId('admin-poi-operation-confirm').click();

  await expect(page.getByTestId('admin-poi-operation-result')).toContainText('move 완료');
  await expect(page.getByTestId('admin-poi-audit-list')).toContainText('poi.move');
  expect(moveBody).toMatchObject({
    target_trip_id: tripId,
    target_day_index: 2,
    attachment_policy: 'move',
    comment_policy: 'move',
    access_reason: 'POI 일정 조정',
  });
});
