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

  await page.goto('/admin/dedup-review');
  await expect(page.getByRole('heading', { name: 'Dedup review' })).toBeVisible();
  await expect(page.getByTestId('admin-dedup-row-review-1')).toBeVisible();

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
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/integrity/issues',
    async (route) => {
      seenIssueUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [integrityIssue],
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

  await page.goto('/admin/integrity');
  await expect(page.getByRole('heading', { name: '정합성' })).toBeVisible();
  await expect(page.getByTestId('admin-integrity-issue-row-issue-1')).toBeVisible();
  await expect(page.getByTestId('admin-integrity-report-row-report-1')).toBeVisible();

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
  expect(reportUrl.searchParams.get('severity_max')).toBe('ERROR');
});

test('Debug logs 페이지가 system/API log 필터를 proxy query로 전달한다', async ({ page }) => {
  const seenSystemUrls: string[] = [];
  const seenApiUrls: string[] = [];
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

  await page.goto('/admin/debug/logs');
  await expect(page.getByRole('heading', { name: 'Debug logs' })).toBeVisible();
  await expect(page.getByTestId('admin-debug-system-row-sys-1')).toBeVisible();
  await expect(page.getByTestId('admin-debug-api-row-api-1')).toBeVisible();

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
});
