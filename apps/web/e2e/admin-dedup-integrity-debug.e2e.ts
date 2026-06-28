import { expect, test } from '@playwright/test';

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

const dedupReview = {
  review_id: 'review-1',
  status: 'pending',
  total_score: 91.4,
  name_score: 94,
  spatial_score: 88,
  category_score: 92,
  distance_m: 32.7,
  feature_a: {
    feature_id: 'feature-a',
    name: '서울타워',
    kind: 'place',
    category: 'tourism',
    lon: 126.9882,
    lat: 37.5512,
    provider: 'visitkorea',
    dataset_key: 'attractions',
  },
  feature_b: {
    feature_id: 'feature-b',
    name: '남산서울타워',
    kind: 'place',
    category: 'tourism',
    lon: 126.9881,
    lat: 37.5513,
    provider: 'kma',
    dataset_key: 'poi_weather',
  },
  decision_reason: null,
  reviewed_at: null,
  reviewed_by: null,
  created_at: '2026-06-12T00:00:00+09:00',
};

const integrityIssue = {
  issue_id: 'issue-1',
  source: 'kor_travel_map',
  violation_type: 'missing_geometry',
  severity: 'critical',
  message: '좌표가 비어 있습니다.',
  payload: { field: 'coord_4326' },
  status: 'open',
  detected_at: '2026-06-12T00:01:00+09:00',
  provider: 'visitkorea',
  dataset_key: 'attractions',
  feature_id: 'feature-a',
  source_record_key: 'visitkorea:1',
  resolved_at: null,
};

const appIntegrityIssue = {
  issue_id: 'pinvi-app-issue-1',
  source: 'pinvi_app',
  violation_type: 'broken_poi_feature_link',
  severity: 'warning',
  message: '여행 POI의 feature 링크가 끊어진 상태입니다.',
  payload: { trip_id: 'trip-1', day_index: 1 },
  status: 'open',
  detected_at: '2026-06-12T00:01:30+09:00',
  provider: null,
  dataset_key: null,
  feature_id: 'feature-pinvi',
  source_record_key: 'trip_day_pois:poi-1',
  resolved_at: null,
};

const consistencyReport = {
  report_id: 'report-1',
  batch_id: 'batch-1',
  started_at: '2026-06-12T00:00:00+09:00',
  finished_at: '2026-06-12T00:05:00+09:00',
  severity_max: 'ERROR',
  cases: [{ name: 'geometry_not_null', failed: 1 }],
  summary: { failed: 1 },
};

const systemLog = {
  log_id: 'sys-1',
  level: 'error',
  source: 'api',
  event: 'upstream.failure',
  message: 'provider timeout',
  detail: { provider: 'visitkorea' },
  request_id: 'req-1',
  created_at: '2026-06-12T00:02:00+09:00',
};

const apiCallLog = {
  log_id: 'api-1',
  method: 'GET',
  path: '/v1/features/search',
  status_code: 503,
  duration_ms: 742,
  request_id: 'req-1',
  error_code: 'UPSTREAM_TIMEOUT',
  created_at: '2026-06-12T00:02:01+09:00',
};

const debugLogStreamStatus = {
  mode: 'polling',
  status: 'ok',
  poll_interval_ms: 500,
  sources: ['kor_travel_map_system_logs', 'kor_travel_map_api_call_logs'],
  loki_enabled: false,
  sse_enabled: false,
  message: 'sanitized polling fallback',
};

const timelineRequestId = '11111111-2222-4333-8444-555555555555';

const requestTimeline = {
  request_id: timelineRequestId,
  generated_at: '2026-06-12T00:03:00+09:00',
  status: 'partial',
  started_at: '2026-06-12T00:02:00+09:00',
  finished_at: '2026-06-12T00:02:01+09:00',
  duration_ms: 1000,
  sources: [
    {
      source: 'pinvi_api_call_log',
      status: 'ok',
      event_count: 1,
      message: null,
    },
    {
      source: 'kor_travel_map_system_logs',
      status: 'degraded',
      event_count: 0,
      message: 'kor_travel_map system log 조회 실패',
    },
  ],
  events: [
    {
      event_id: 'pinvi_api_call:1',
      occurred_at: '2026-06-12T00:02:00+09:00',
      source: 'pinvi_api_call_log',
      title: 'kor_travel_map API call',
      status: '503',
      duration_ms: 742,
      error_code: 'UPSTREAM_TIMEOUT',
      detail: {
        provider: 'kor_travel_map',
        endpoint: '/v1/features?token=[masked]',
        has_error_message: true,
      },
    },
  ],
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

test('Dedup review 페이지가 후보 행과 필터 query를 표시한다', async ({ page }) => {
  const seenUrls: string[] = [];
  let decisionBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/dedup-review',
    async (route) => {
      seenUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [dedupReview],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/dedup-review/review-1/verdict',
    async (route) => {
      decisionBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            review_id: 'review-1',
            decision: 'merged',
            changed: true,
            master_feature_id: 'feature-a',
            loser_feature_id: 'feature-b',
            merge_id: 'merge-1',
            source_links_moved: 2,
            source_links_dropped: 0,
          },
        }),
      });
    },
  );

  await page.goto('/admin/dedup-review');
  await expect(page.getByRole('heading', { name: 'Dedup review' })).toBeVisible();
  await expect(page.getByTestId('admin-dedup-row-review-1')).toBeVisible();
  await page.getByTestId('admin-dedup-row-review-1').click();

  await page.getByTestId('admin-dedup-access-reason').fill('중복 후보 병합');
  await page.getByTestId('admin-dedup-map-reason').fill('동일 장소 확인');
  await page.getByTestId('admin-dedup-submit-verdict').click();
  await expect(page.getByTestId('admin-dedup-mutation-notice')).toContainText('병합');
  expect(decisionBody).toEqual({
    decision: 'merged',
    access_reason: '중복 후보 병합',
    kor_travel_map_reason: '동일 장소 확인',
    master_feature_id: 'feature-a',
  });

  await page.getByTestId('admin-dedup-search').fill('seoul');
  await page.getByTestId('admin-dedup-min-score').fill('85');
  await page.getByTestId('admin-dedup-submit').click();
  await page.getByTestId('admin-dedup-status').selectOption('accepted');
  await expect(page.getByTestId('admin-dedup-row-review-1')).toBeVisible();

  const lastUrl = new URL(seenUrls[seenUrls.length - 1]!);
  expect(lastUrl.searchParams.get('q')).toBe('seoul');
  expect(lastUrl.searchParams.get('min_score')).toBe('85');
  expect(lastUrl.searchParams.getAll('status')).toContain('accepted');
});

test('정합성 페이지가 issue/report와 각각의 필터 query를 표시한다', async ({ page }) => {
  const seenIssueUrls: string[] = [];
  const seenReportUrls: string[] = [];
  let actionBody: Record<string, unknown> | null = null;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/integrity/issues',
    async (route) => {
      seenIssueUrls.push(route.request().url());
      const requestUrl = new URL(route.request().url());
      const item =
        requestUrl.searchParams.get('source') === 'pinvi_app' ? appIntegrityIssue : integrityIssue;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [item],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/integrity/reports',
    async (route) => {
      seenReportUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [consistencyReport],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/integrity/issues/issue-1/action',
    async (route) => {
      actionBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            action: 'resolve',
            issue: {
              ...integrityIssue,
              status: 'resolved',
              resolved_at: '2026-06-12T00:03:00+09:00',
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/integrity');
  await expect(page.getByRole('heading', { name: '정합성' })).toBeVisible();
  await expect(page.getByTestId('admin-integrity-issue-row-issue-1')).toBeVisible();
  await expect(page.getByTestId('admin-integrity-report-row-report-1')).toBeVisible();

  await page.getByTestId('admin-integrity-action-resolve-issue-1').click();
  await expect(page.getByTestId('admin-integrity-action-dialog')).toBeVisible();
  await page.getByTestId('admin-integrity-action-access-reason').fill('원천 데이터 확인');
  await page.getByTestId('admin-integrity-action-map-reason').fill('source verified');
  await page.getByTestId('admin-integrity-action-submit').click();
  await expect(page.getByTestId('admin-integrity-action-notice')).toContainText('해결');
  expect(actionBody).toEqual({
    action: 'resolve',
    access_reason: '원천 데이터 확인',
    kor_travel_map_reason: 'source verified',
  });

  await page.getByTestId('admin-integrity-status').selectOption('acknowledged');
  await page.getByTestId('admin-integrity-severity').selectOption('critical');
  await page.getByTestId('admin-integrity-provider').fill('visitkorea');
  await page.getByTestId('admin-integrity-report-severity').selectOption('ERROR');
  await expect(page.getByTestId('admin-integrity-issue-row-issue-1')).toBeVisible();
  await expect(page.getByTestId('admin-integrity-report-row-report-1')).toBeVisible();

  const issueUrl = new URL(seenIssueUrls[seenIssueUrls.length - 1]!);
  const reportUrl = new URL(seenReportUrls[seenReportUrls.length - 1]!);
  expect(issueUrl.searchParams.get('status')).toBe('acknowledged');
  expect(issueUrl.searchParams.get('severity')).toBe('critical');
  expect(issueUrl.searchParams.get('provider')).toBe('visitkorea');
  expect(issueUrl.searchParams.get('source')).toBe('all');
  expect(reportUrl.searchParams.get('severity_max')).toBe('ERROR');

  await page.getByTestId('admin-integrity-provider').fill('');
  await page.getByTestId('admin-integrity-severity').selectOption('all');
  await page.getByTestId('admin-integrity-source').selectOption('pinvi_app');
  await expect(page.getByTestId('admin-integrity-issue-row-pinvi-app-issue-1')).toBeVisible();
  await expect(page.getByTestId('admin-integrity-issue-row-pinvi-app-issue-1')).toContainText(
    'read-only',
  );
  await expect(page.getByTestId('admin-integrity-action-resolve-pinvi-app-issue-1')).toHaveCount(0);
  const appIssueUrl = new URL(seenIssueUrls[seenIssueUrls.length - 1]!);
  expect(appIssueUrl.searchParams.get('source')).toBe('pinvi_app');
});

test('Debug logs 페이지가 system/API log 필터를 proxy query로 전달한다', async ({ page }) => {
  const seenSystemUrls: string[] = [];
  const seenApiUrls: string[] = [];
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/debug/logs/stream/status',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: debugLogStreamStatus }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/debug/logs/system',
    async (route) => {
      seenSystemUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [systemLog],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/debug/logs/api-calls',
    async (route) => {
      seenApiUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [apiCallLog],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === `/admin/debug/request/${timelineRequestId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: requestTimeline }),
      });
    },
  );

  await page.goto('/admin/debug/logs');
  await expect(page.getByRole('heading', { name: 'Debug logs' })).toBeVisible();
  await expect(page.getByTestId('admin-debug-system-row-sys-1')).toBeVisible();
  await expect(page.getByTestId('admin-debug-api-row-api-1')).toBeVisible();
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('polling');
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('off');

  await page.getByTestId('admin-debug-level').selectOption('critical');
  await page.getByTestId('admin-debug-source').fill('worker');
  await page.getByTestId('admin-debug-q').fill('timeout');
  await page.getByTestId('admin-debug-method').fill('POST');
  await page.getByTestId('admin-debug-min-status').fill('500');
  await page.getByTestId('admin-debug-path').fill('/v1/features');
  await page.getByTestId('admin-debug-submit').click();
  await expect(page.getByTestId('admin-debug-system-row-sys-1')).toBeVisible();
  await expect(page.getByTestId('admin-debug-api-row-api-1')).toBeVisible();

  const systemUrl = new URL(seenSystemUrls[seenSystemUrls.length - 1]!);
  const apiUrl = new URL(seenApiUrls[seenApiUrls.length - 1]!);
  expect(systemUrl.searchParams.get('level')).toBe('critical');
  expect(systemUrl.searchParams.get('source')).toBe('worker');
  expect(systemUrl.searchParams.get('q')).toBe('timeout');
  expect(apiUrl.searchParams.get('method')).toBe('POST');
  expect(apiUrl.searchParams.get('min_status')).toBe('500');
  expect(apiUrl.searchParams.get('path')).toBe('/v1/features');

  const systemCountBeforeLive = seenSystemUrls.length;
  await page.getByTestId('admin-debug-live-toggle').click();
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('live');
  await expect
    .poll(() => seenSystemUrls.length, { timeout: 3000 })
    .toBeGreaterThan(systemCountBeforeLive);

  await page.getByTestId('admin-debug-live-pause').click();
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('paused');
  await page.waitForTimeout(100);
  const pausedSystemCount = seenSystemUrls.length;
  await page.waitForTimeout(900);
  expect(seenSystemUrls.length).toBe(pausedSystemCount);

  await page.getByTestId('admin-debug-live-pause').click();
  await expect(page.getByTestId('admin-debug-live-status')).toContainText('live');
  await expect
    .poll(() => seenSystemUrls.length, { timeout: 3000 })
    .toBeGreaterThan(pausedSystemCount);

  await page.getByTestId('admin-debug-request-id').fill(timelineRequestId);
  await page.getByTestId('admin-debug-request-submit').click();
  await expect(page.getByRole('heading', { name: 'Request timeline' })).toBeVisible();
  await expect(page.getByTestId('admin-request-timeline-summary')).toContainText('partial');
  await expect(page.getByTestId('admin-request-source-pinvi_api_call_log')).toBeVisible();
  await expect(page.getByTestId('admin-request-source-kor_travel_map_system_logs')).toBeVisible();
  await expect(page.getByTestId('admin-request-event-pinvi_api_call:1')).toBeVisible();
  await expect(page.getByText('secret')).toHaveCount(0);
});
