import { expect, test } from '@playwright/test';
import type {
  AdminApiCallEntry,
  AdminFeatureDetail,
  AdminFeaturePagedResponse,
  AdminLocationAuditEntry,
  AdminSystemDetail,
  AdminSystemSummary,
} from '@pinvi/schemas';

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin', 'cpo'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

const apiCall: AdminApiCallEntry = {
  log_id: 10,
  provider: 'kma',
  endpoint: '/weather/current',
  status_code: 200,
  latency_ms: 42,
  error_class: null,
  error_message: null,
  request_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  occurred_at: '2026-06-09T10:00:00+09:00',
};

const locationAudit: AdminLocationAuditEntry = {
  log_id: 20,
  user_id: '99999999-9999-4999-8999-999999999999',
  occurred_at: '2026-06-09T11:00:00+09:00',
  endpoint: '/features/in-bounds',
  purpose: 'viewport_query',
  lat_masked: '37.5666',
  lng_masked: '126.9781',
  request_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  ip_hash: 'a'.repeat(64),
  prev_hash: '0'.repeat(64),
  content_hash: '1'.repeat(64),
};

const systemSummary: AdminSystemSummary = {
  generated_at: '2026-06-09T10:00:00+09:00',
  services: [
    {
      key: 'pinvi_api',
      label: 'Pinvi API',
      status: 'ok',
      message: 'admin route 응답 정상',
      latency_ms: 0,
    },
    { key: 'postgres', label: 'DB', status: 'ok', message: 'SELECT 1 정상', latency_ms: 3 },
    { key: 'pinvi_web', label: 'Web', status: 'ok', message: '응답 정상', latency_ms: 6 },
    {
      key: 'dagster',
      label: 'Dagster',
      status: 'unknown',
      message: 'base URL 미설정',
      latency_ms: null,
    },
    {
      key: 'kor_travel_map_api',
      label: 'kor-travel-map API',
      status: 'degraded',
      message: 'HTTP 503',
      latency_ms: 12,
    },
    { key: 'rustfs', label: 'RustFS', status: 'ok', message: '응답 정상', latency_ms: 8 },
  ],
};

const systemDetail: AdminSystemDetail = {
  generated_at: '2026-06-09T10:00:00+09:00',
  dependencies: systemSummary.services,
  docker: {
    key: 'docker',
    label: 'Docker',
    status: 'ok',
    message: '2개 container 수집',
    latency_ms: 5,
  },
  containers: [
    {
      container_id: 'abc123',
      name: 'pinvi-api-latest',
      image: 'pinvi-api:latest-main',
      state: 'running',
      status: 'Up 1 minute (healthy)',
      health: 'healthy',
      compose_project: 'pinvi',
      compose_service: 'pinvi-api',
    },
    {
      container_id: 'def456',
      name: 'pinvi-web-latest',
      image: 'pinvi-web:latest-main',
      state: 'running',
      status: 'Up 1 minute (healthy)',
      health: 'healthy',
      compose_project: 'pinvi',
      compose_service: 'pinvi-web',
    },
  ],
};

const featurePage: AdminFeaturePagedResponse = {
  items: [
    {
      feature_id: 'f_place_1',
      kind: 'place',
      name: '해운대 카페',
      category: '01070100',
      lifecycle_state: 'active',
      publication_state: 'published',
      quality_state: 'valid',
      lon: 129.163,
      lat: 35.158,
      address_label: '부산 해운대구',
      primary_provider: 'visitkorea',
      primary_dataset_key: 'places',
      issue_count: 1,
      issues: [
        {
          issue_id: 'iss-1',
          violation_type: 'missing_source',
          severity: 'warning',
          message: 'source 보강 필요',
          detected_at: '2026-06-12T00:00:00+09:00',
        },
      ],
      created_at: '2026-06-11T00:00:00+09:00',
      updated_at: '2026-06-12T00:00:00+09:00',
    },
  ],
  page_size: 50,
  next_cursor: 'cursor-2',
  duration_ms: 7,
};

const featureDetail: AdminFeatureDetail = {
  feature: {
    feature_id: 'f_place_1',
    kind: 'place',
    name: '해운대 카페',
    category: '01070100',
    lifecycle_state: 'active',
    publication_state: 'published',
    quality_state: 'valid',
    lon: 129.163,
    lat: 35.158,
    coord_precision_digits: null,
    area_square_meters: null,
    address: { road: '해운대해변로' },
    detail: { phone: '051-000-0000' },
    urls: { homepage: 'https://example.com/place' },
    raw_refs: [{ provider: 'visitkorea' }],
    legal_dong_code: null,
    road_name_code: null,
    road_address_management_no: null,
    admin_dong_code: null,
    sido_code: '26',
    sigungu_code: '26350',
    marker_icon: 'cafe',
    marker_color: 'P-07',
    parent_feature_id: null,
    sibling_group_id: null,
    // Map `AdminFeatureDetailFeatureRecord`에는 `data_origin`/`data_version`이 **없다**
    // (3축 cutover `1f2bdc3a`). Pinvi schema가 optional로 남겨 둔 필드라 fixture는 실제
    // 응답과 같은 null이어야 한다 — 값을 넣으면 "Map이 준다"는 거짓을 e2e가 고정한다.
    data_origin: null,
    data_version: null,
    user_change_kind: null,
    user_change_status: null,
    user_change_request_id: null,
    user_deleted_at: null,
    user_deleted_by: null,
    user_change_reason: null,
    created_at: '2026-06-11T00:00:00+09:00',
    updated_at: '2026-06-12T00:00:00+09:00',
    deleted_at: null,
  },
  sources: [
    {
      source_record_key: 'visitkorea:places:1',
      provider: 'visitkorea',
      dataset_key: 'places',
      source_entity_type: 'content',
      source_entity_id: '1',
      source_version: null,
      source_role: 'primary',
      match_method: 'natural_key',
      confidence: 100,
      // Map `AdminFeatureDetailSourceRecord`에 `is_primary_source`는 없다 — primary 여부는
      // `source_role`이 표현한다.
      is_primary_source: null,
      raw_name: '해운대 카페',
      raw_address: null,
      raw_longitude: null,
      raw_latitude: null,
      raw_payload_hash: 'sha256:abc',
      raw_data: { name: '해운대 카페' },
      fetched_at: '2026-06-11T00:00:00+09:00',
      imported_at: '2026-06-11T00:01:00+09:00',
      expires_at: null,
      linked_at: '2026-06-11T00:02:00+09:00',
    },
  ],
  issues: [],
  overrides: [],
  // Map admin 상세 payload에는 `versions`/`change_requests`가 없다(있는 list는 sources /
  // issues / overrides / files / state_transitions / curations). Pinvi는 두 키를 소비자
  // 호환용으로 남겨 두지만 값은 늘 비어 있으므로 fixture도 비운다.
  versions: [],
  change_requests: [],
  files: [],
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

test('Admin Features가 Pinvi proxy로 목록 필터와 상세를 조회한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/features',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: featurePage }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/features/f_place_1',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: featureDetail }),
      });
    },
  );

  await page.goto('/admin/features');

  await expect(page.getByRole('heading', { name: 'Features' })).toBeVisible();
  await expect(page.getByTestId('admin-features-row-f_place_1')).toContainText('해운대 카페');

  await page.getByTestId('admin-features-search').fill('해운대');
  await page.getByTestId('admin-features-provider-dataset-filter').fill('42');
  await page.getByTestId('admin-features-category-filter').fill('01070100');
  await page.getByTestId('admin-features-search-submit').click();
  await page.getByTestId('admin-features-kind-filter').selectOption('place');
  await page.getByTestId('admin-features-lifecycle-filter').selectOption('active');
  await page.getByTestId('admin-features-publication-filter').selectOption('suppressed');
  await page.getByTestId('admin-features-quality-filter').selectOption('quarantined');
  await page.getByTestId('admin-features-issue-filter').selectOption('yes');

  // Map 3축 cutover(`1f2bdc3a`) 이후의 query 이름만 나가야 한다. legacy 이름은
  // upstream이 조용히 버리므로 "필터가 걸린 척"하는 회귀를 여기서 잡는다.
  await expect
    .poll(() =>
      requests.some(
        (url) =>
          url.includes('q=') &&
          url.includes('provider_dataset_id=42') &&
          url.includes('category=01070100') &&
          url.includes('kind=place') &&
          url.includes('lifecycle_state=active') &&
          url.includes('publication_state=suppressed') &&
          url.includes('quality_state=quarantined') &&
          url.includes('has_issue=true'),
      ),
    )
    .toBe(true);
  expect(requests.some((url) => /[?&]status=/.test(url))).toBe(false);
  expect(requests.some((url) => /[?&]provider=/.test(url))).toBe(false);
  expect(requests.some((url) => /[?&]dataset_key=/.test(url))).toBe(false);

  await page.getByTestId('admin-features-detail-f_place_1').click();
  await expect(page.getByTestId('admin-features-detail')).toContainText('visitkorea / places');
  await expect(page.getByTestId('admin-features-detail')).toContainText('해운대해변로');
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('Admin 대시보드가 앱 소유 통계를 표시한다', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/stats/overview',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            generated_at: '2026-06-09T10:00:00+09:00',
            users_total: 12,
            users_24h: 3,
            users_pending_verification: 2,
            trips_total: 7,
            trips_active: 4,
            pois_total: 31,
            email_queue_pending: 5,
            api_calls_24h: 21,
            api_calls_failed_24h: 1,
            api_failure_rate_pct: 4.8,
            api_latency_p95_ms: 320,
            features_by_kind: {},
            etl_last_24h: { success: 0, failed: 0 },
            series_24h: Array.from({ length: 24 }, (_, index) => ({
              bucket_start: `2026-06-09T${String(index).padStart(2, '0')}:00:00+09:00`,
              users_created: index === 22 ? 2 : 0,
              trips_created: index === 23 ? 1 : 0,
              api_calls: index + 1,
              api_failures: index === 23 ? 1 : 0,
            })),
            load: {
              cpu_count: 4,
              load_1m: 0.7,
              load_5m: 0.5,
              load_15m: 0.4,
            },
            capacity: {
              attachments_total_bytes: 20971520,
              attachments_count: 8,
              trip_attachment_quota_bytes: 104857600,
              user_attachment_quota_bytes: 1073741824,
              attachment_max_upload_bytes: 10485760,
              avatar_max_upload_bytes: 2097152,
              users_with_quota_override: 2,
              disk_total_bytes: 107374182400,
              disk_used_bytes: 32212254720,
              disk_free_bytes: 75161927680,
            },
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/system/summary',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: systemSummary }),
      });
    },
  );

  await page.goto('/admin');

  await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
  await expect(page.getByTestId('admin-system-pinvi_api')).toContainText('정상');
  await expect(page.getByTestId('admin-system-kor_travel_map_api')).toContainText('주의');
  await expect(page.getByTestId('admin-stat-사용자 총 수')).toContainText('12');
  await expect(page.getByTestId('admin-stat-API 실패 24h')).toContainText('1');
  await expect(page.getByTestId('admin-stat-API P95')).toContainText('320 ms');
  await expect(page.getByTestId('admin-dashboard-series-api')).toContainText('API 호출 / 실패');
  await expect(page.getByTestId('admin-dashboard-series-growth')).toContainText('가입 / 여행 생성');
  await expect(page.getByTestId('admin-dashboard-load')).toContainText('0.70');
  await expect(page.getByTestId('admin-dashboard-capacity-disk')).toContainText('30.0%');
  await expect(page.getByTestId('admin-dashboard-capacity')).toContainText('8 files');
  await expect(page.getByText('T-209 Feature 검색')).toBeVisible();
});

test('Admin 시스템 화면이 의존 API와 Docker 상태를 표시한다', async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/system/detail',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: systemDetail }),
      });
    },
  );

  await page.goto('/admin/system');

  await expect(page.getByRole('heading', { name: '시스템', exact: true })).toBeVisible();
  await expect(page.getByTestId('admin-system-dependency-pinvi_api')).toContainText('정상');
  await expect(page.getByTestId('admin-system-dependency-kor_travel_map_api')).toContainText(
    '주의',
  );
  await expect(page.getByTestId('admin-system-docker')).toContainText('2개 container 수집');
  await expect(page.getByTestId('admin-system-containers')).toContainText('pinvi-api-latest');
  await expect(page.getByTestId('admin-system-containers')).toContainText('pinvi-web:latest-main');
});

test('Admin API 호출 로그가 필터를 API에 전달한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/api-calls',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [apiCall] }),
      });
    },
  );

  await page.goto('/admin/api-calls');

  await expect(page.getByRole('heading', { name: 'API 호출 로그' })).toBeVisible();
  await expect(page.getByText('/weather/current')).toBeVisible();

  await page.getByTestId('admin-api-calls-provider').fill('kma');
  await page.getByTestId('admin-api-calls-status').fill('200');
  await page.getByTestId('admin-api-calls-submit').click();

  await expect
    .poll(() =>
      requests.some((url) => url.includes('provider=kma') && url.includes('status_code=200')),
    )
    .toBe(true);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});

test('CPO 위치 감사 로그가 마스킹 좌표와 날짜 필터를 표시한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/audit/location',
    async (route) => {
      requests.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [locationAudit] }),
      });
    },
  );

  await page.goto('/admin/audit/location');

  await expect(page.getByRole('heading', { name: '위치 감사 로그' })).toBeVisible();
  await expect(page.getByText('126.9781, 37.5666')).toBeVisible();
  await expect(page.getByText('37.566567')).toHaveCount(0);

  await page.getByTestId('admin-location-user').fill(locationAudit.user_id);
  await page.getByTestId('admin-location-from').fill('2026-06-09T00:00');
  await page.getByTestId('admin-location-to').fill('2026-06-10T00:00');
  await page.getByTestId('admin-location-submit').click();

  await expect
    .poll(() =>
      requests.some(
        (url) =>
          url.includes(`user_id=${locationAudit.user_id}`) &&
          url.includes('from=') &&
          url.includes('to='),
      ),
    )
    .toBe(true);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});
