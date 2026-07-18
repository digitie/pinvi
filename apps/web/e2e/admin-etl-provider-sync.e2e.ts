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

const jobId = '11111111-1111-4111-8111-111111111111';
const projectedJobId = '22222222-2222-4222-8222-222222222222';
const cancellationId = '33333333-3333-4333-8333-333333333333';

const importJob = {
  job_id: jobId,
  kind: 'import_job',
  status: 'running',
  progress: 1,
  projected_job_id: projectedJobId,
  projected_job_kind: 'provider_import',
  projected_job_status: 'running',
  projected_job_progress: 1,
  projected_job_load_batch_id: null,
  projected_job_parent_job_id: null,
  cancellation: null,
  payload: { provider: 'kma' },
  status_url: `/v1/ops/pipeline/executions/import_job/${jobId}`,
  current_stage: 'normalize',
  error_message: null,
  created_at: '2026-06-12T00:00:00+09:00',
  started_at: '2026-06-12T00:01:00+09:00',
  finished_at: null,
  links: {},
};

const cancellationOverlayJobs = [
  ['55555555-5555-4555-8555-555555555555', 'in_progress'],
  ['66666666-6666-4666-8666-666666666666', 'retryable'],
  ['88888888-8888-4888-8888-888888888888', 'failed'],
  ['99999999-9999-4999-8999-999999999999', 'completed'],
].map(([overlayJobId, status], index) => ({
  ...importJob,
  job_id: overlayJobId,
  projected_job_id: overlayJobId,
  cancellation: {
    cancellation_id: `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa${index}`,
    status,
    requested_at: '2026-06-12T00:02:00+09:00',
    requested_by: 'service:pinvi',
    reason: 'overlay fixture',
    retryable: status === 'retryable',
    unresolved_member_count: status === 'retryable' ? 1 : 0,
  },
}));

const provider = {
  provider: 'kma',
  dataset_key: 'special_days',
  sync_scope: 'daily',
  status: 'healthy',
  last_success_at: '2026-06-12T00:00:00+09:00',
  last_failure_at: null,
  consecutive_failures: 0,
  eligible_after: '2026-06-13T03:30:00+09:00',
  schedule_next_scheduled_at: '2026-06-14T03:30:00+09:00',
  links: {},
  refresh_policy: { enabled: true },
};

const etlSummary = {
  generated_at: '2026-06-12T00:03:00+09:00',
  pinvi: {
    status: 'ok',
    message: 'Dagster server_info/live snapshot 정상',
    latency_ms: 10,
    checked_at: '2026-06-12T00:03:00+09:00',
    dagster_version: '1.13.11',
    dagster_webserver_version: '1.13.11',
    dagster_graphql_version: '1.13.11',
    repository_count: 1,
    job_count: 6,
    asset_count: 5,
    schedule_count: 5,
    sensor_count: 0,
    repositories: [
      {
        name: '__repository__',
        location_name: 'pinvi.etl.definitions',
        jobs: [
          { name: 'kasi_special_days_job', is_job: true },
          { name: 'kasi_poi_rise_set_job', is_job: true },
          { name: 'pinvi_email_outbox_job', is_job: true },
          { name: 'pinvi_telegram_system_outbox_job', is_job: true },
          { name: 'pinvi_pii_retention_job', is_job: true },
          { name: 'pinvi_location_log_archive_job', is_job: true },
        ],
        schedules: [
          {
            name: 'kasi_special_days_schedule',
            job_name: 'kasi_special_days_job',
            cron_schedule: '30 3 * * *',
            execution_timezone: 'Asia/Seoul',
            status: 'RUNNING',
          },
          {
            name: 'pinvi_email_outbox_schedule',
            job_name: 'pinvi_email_outbox_job',
            cron_schedule: '*/15 * * * *',
            execution_timezone: 'Asia/Seoul',
            status: 'RUNNING',
          },
          {
            name: 'pinvi_telegram_system_outbox_schedule',
            job_name: 'pinvi_telegram_system_outbox_job',
            cron_schedule: '*/15 * * * *',
            execution_timezone: 'Asia/Seoul',
            status: 'RUNNING',
          },
          {
            name: 'pinvi_pii_retention_schedule',
            job_name: 'pinvi_pii_retention_job',
            cron_schedule: '15 4 * * *',
            execution_timezone: 'Asia/Seoul',
            status: 'RUNNING',
          },
          {
            name: 'pinvi_location_log_archive_schedule',
            job_name: 'pinvi_location_log_archive_job',
            cron_schedule: '30 4 * * *',
            execution_timezone: 'Asia/Seoul',
            status: 'RUNNING',
          },
        ],
        sensors: [],
        asset_count: 5,
        asset_groups: ['pinvi_email', 'pinvi_kasi', 'pinvi_retention', 'pinvi_telegram'],
      },
    ],
    recent_runs: [
      {
        run_id: 'pinvi-run-1',
        status: 'SUCCESS',
        job_name: 'pinvi_email_outbox_job',
        start_time: 1781190000,
        end_time: 1781190010,
        update_time: 1781190010,
        tags: {},
      },
    ],
    assets: [
      {
        key: 'pinvi_kasi_special_days',
        group_name: 'pinvi_kasi',
        description: 'KASI 특일·공휴일 기준 데이터',
      },
      {
        key: 'pinvi_email_outbox',
        group_name: 'pinvi_email',
        description: 'email_queue 상태',
      },
      {
        key: 'pinvi_telegram_system_outbox',
        group_name: 'pinvi_telegram',
        description: 'telegram_system_notification_outbox 상태',
      },
      {
        key: 'pinvi_pii_retention',
        group_name: 'pinvi_retention',
        description: 'PII 보존 기간 만료 후보 dry-run',
      },
      {
        key: 'pinvi_location_log_archive',
        group_name: 'pinvi_retention',
        description: 'location_access_log archive 후보 dry-run',
      },
    ],
    jobs: [
      {
        name: 'kasi_special_days_job',
        trigger: 'schedule',
        description: '매일 KST 03:30 KASI 특일 데이터를 갱신합니다.',
        asset_keys: ['pinvi_kasi_special_days'],
      },
      {
        name: 'kasi_poi_rise_set_job',
        trigger: 'on_demand',
        description: 'POI별 일출·일몰 보강을 1회 실행합니다.',
        asset_keys: [],
      },
      {
        name: 'pinvi_email_outbox_job',
        trigger: 'schedule',
        description: '15분마다 email_queue 상태와 template별 실패율을 점검합니다.',
        asset_keys: ['pinvi_email_outbox'],
      },
      {
        name: 'pinvi_telegram_system_outbox_job',
        trigger: 'schedule',
        description: '15분마다 Telegram system outbox 상태를 점검합니다.',
        asset_keys: ['pinvi_telegram_system_outbox'],
      },
      {
        name: 'pinvi_pii_retention_job',
        trigger: 'schedule',
        description: '매일 KST 04:15 PII 보존 기간 만료 후보를 dry-run으로 점검합니다.',
        asset_keys: ['pinvi_pii_retention'],
      },
      {
        name: 'pinvi_location_log_archive_job',
        trigger: 'schedule',
        description: '매일 KST 04:30 위치 접근 로그 archive 후보와 chain bridge 상태를 점검합니다.',
        asset_keys: ['pinvi_location_log_archive'],
      },
    ],
    schedules: [
      {
        name: 'kasi_special_days_schedule',
        job_name: 'kasi_special_days_job',
        cron_schedule: '30 3 * * *',
        execution_timezone: 'Asia/Seoul',
        status: 'configured',
      },
      {
        name: 'pinvi_email_outbox_schedule',
        job_name: 'pinvi_email_outbox_job',
        cron_schedule: '*/15 * * * *',
        execution_timezone: 'Asia/Seoul',
        status: 'configured',
      },
      {
        name: 'pinvi_telegram_system_outbox_schedule',
        job_name: 'pinvi_telegram_system_outbox_job',
        cron_schedule: '*/15 * * * *',
        execution_timezone: 'Asia/Seoul',
        status: 'configured',
      },
      {
        name: 'pinvi_pii_retention_schedule',
        job_name: 'pinvi_pii_retention_job',
        cron_schedule: '15 4 * * *',
        execution_timezone: 'Asia/Seoul',
        status: 'configured',
      },
      {
        name: 'pinvi_location_log_archive_schedule',
        job_name: 'pinvi_location_log_archive_job',
        cron_schedule: '30 4 * * *',
        execution_timezone: 'Asia/Seoul',
        status: 'configured',
      },
    ],
    sensors: [],
    email_outbox: {
      total: 4,
      pending_total: 2,
      pending_due: 1,
      pending_backoff: 1,
      stuck_pending: 1,
      failed: 1,
      bounced: 1,
      complained: 0,
      retry_exhausted: 1,
      oldest_pending_scheduled_at: '2026-06-12T00:00:00+09:00',
      stuck_threshold_minutes: 15,
      max_attempts: 5,
      template_window_hours: 24,
      template_stats: [
        {
          template: 'verify_email',
          total: 3,
          pending: 2,
          sent: 0,
          delivered: 0,
          failed: 1,
          bounced: 0,
          complained: 0,
          failure_count: 1,
          failure_rate: 0.3333,
        },
        {
          template: 'trip_invite',
          total: 1,
          pending: 0,
          sent: 0,
          delivered: 0,
          failed: 0,
          bounced: 1,
          complained: 0,
          failure_count: 1,
          failure_rate: 1,
        },
      ],
    },
    telegram_outbox: {
      total: 5,
      pending_total: 2,
      pending_due: 1,
      pending_backoff: 1,
      stuck_pending: 1,
      sent: 1,
      skipped: 1,
      failed: 1,
      retry_exhausted: 2,
      oldest_pending_scheduled_at: '2026-06-12T00:00:00+09:00',
      stuck_threshold_minutes: 15,
      max_attempts: 5,
      category_window_hours: 24,
      category_stats: [
        {
          category: 'trip_created',
          total: 3,
          pending: 1,
          sent: 0,
          skipped: 1,
          failed: 1,
          retry_exhausted: 2,
          retry_exhausted_rate: 0.6667,
        },
        {
          category: 'companion_invited',
          total: 2,
          pending: 1,
          sent: 1,
          skipped: 0,
          failed: 0,
          retry_exhausted: 0,
          retry_exhausted_rate: 0,
        },
      ],
    },
    pii_retention: {
      dry_run: true,
      generated_at: '2026-06-12T00:03:00+09:00',
      user_pii_cutoff: '2026-05-13T00:03:00+09:00',
      session_cutoff: '2026-05-13T00:03:00+09:00',
      user_pii_grace_days: 30,
      session_grace_days: 30,
      total_candidates: 10,
      deleted_user_pii_candidates: 2,
      deleted_user_oauth_identity_candidates: 1,
      excluded_privileged_deleted_users: 1,
      expired_signup_verifications: 2,
      expired_password_reset_tokens: 1,
      old_revoked_sessions: 1,
      old_expired_sessions: 1,
      expired_oauth_login_states: 1,
      expired_mobile_oauth_exchanges: 1,
    },
    audit_retention: {
      dry_run: true,
      generated_at: '2026-06-12T00:03:00+09:00',
      audit_cutoff: '2026-03-14T00:03:00+09:00',
      audit_retention_days: 90,
      policy: 'append_only_cold_storage',
      admin_audit_pii_over_retention: 0,
    },
    location_log_archive: {
      dry_run: true,
      generated_at: '2026-06-12T00:03:00+09:00',
      archive_cutoff: '2025-12-12T00:03:00+09:00',
      location_retention_months: 6,
      total_candidates: 1,
      oldest_candidate_at: '2025-12-11T00:03:00+09:00',
      newest_candidate_at: '2025-12-11T00:03:00+09:00',
      archive_tail_log_id: 10,
      active_head_log_id: 11,
      active_rows_after_cutoff: 1,
      chain_bridge_required: true,
      bridge_anchor_matches: true,
      pending_outbox_total: 1,
      pending_outbox_before_cutoff: 0,
      archive_blocked_by_pending_outbox: false,
      oldest_pending_outbox_at: '2026-06-11T00:03:00+09:00',
      purpose_stats: [{ purpose: 'nearby_attractions', total: 1 }],
    },
  },
  kor_travel_map: {
    status: 'ok',
    dagster_status: 'ok',
    checked_at: '2026-06-12T00:00:00+09:00',
    repository_count: null,
    job_count: null,
    asset_count: null,
    schedule_count: 2,
    sensor_count: 0,
    run_counts: { STARTED: 1 },
    dagster_errors: [],
    operations_by_status: { queued: 0, running: 1, done: 9, failed: 0, cancelled: 0 },
    active_operations: 1,
    failed_operations_24h: 0,
    recent_runs: [
      {
        run_id: 'run-1',
        status: 'STARTED',
        job_name: 'kma_special_days_job',
        start_time: 1781190000,
        end_time: null,
        update_time: 1781190010,
        tags: {},
      },
    ],
    features_total: null,
    source_records_total: null,
    provider_dataset_count: 1,
    provider_failure_count: 0,
    recent_import_jobs: [importJob],
    errors: [],
  },
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

test('ETL 페이지가 Pinvi 실제 Dagster 정의와 upstream import job을 표시한다', async ({ page }) => {
  const seenJobUrls: string[] = [];
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/etl/summary',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: etlSummary }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      seenJobUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [importJob],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );

  await page.goto('/admin/etl');
  await expect(page.getByRole('heading', { name: 'ETL' })).toBeVisible();
  await expect(page.getByTestId('admin-etl-pinvi-status')).toContainText('정상');
  await expect(page.getByTestId('admin-etl-pinvi-live-repository-count')).toContainText('1');
  await expect(page.getByTestId('admin-etl-pinvi-live-job-count')).toContainText('6');
  await expect(page.getByTestId('admin-etl-pinvi-live-schedule-count')).toContainText('5');
  await expect(page.getByTestId('admin-etl-job-kasi_special_days_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-kasi_poi_rise_set_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_email_outbox_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_telegram_system_outbox_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_pii_retention_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_location_log_archive_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_email_outbox_job-live')).toContainText('live');
  await expect(page.getByTestId('admin-etl-job-pinvi_email_outbox_job-timezone')).toContainText(
    'Asia/Seoul',
  );
  await expect(page.getByTestId('admin-etl-job-pinvi_email_outbox_job-latest-run')).toContainText(
    'SUCCESS',
  );
  await expect(page.getByTestId('admin-etl-pinvi-live-repositories')).toContainText(
    'pinvi.etl.definitions',
  );
  await expect(
    page.getByTestId('admin-etl-pinvi-live-schedule-pinvi_email_outbox_schedule'),
  ).toContainText('Asia/Seoul');
  await expect(page.getByTestId('admin-etl-pinvi-live-runs')).toContainText(
    'pinvi_email_outbox_job',
  );
  await expect(page.getByTestId('admin-etl-email-outbox')).toContainText('backoff');
  await expect(page.getByTestId('admin-etl-email-stuck')).toContainText('1');
  await expect(page.getByTestId('admin-etl-email-template-verify_email')).toContainText('33.3%');
  await expect(page.getByTestId('admin-etl-telegram-outbox')).toContainText('backoff');
  await expect(page.getByTestId('admin-etl-telegram-stuck')).toContainText('1');
  await expect(page.getByTestId('admin-etl-telegram-category-trip_created')).toContainText('66.7%');
  await expect(page.getByTestId('admin-etl-pii-retention')).toContainText('dry-run');
  await expect(page.getByTestId('admin-etl-pii-total')).toContainText('10');
  await expect(page.getByTestId('admin-etl-pii-tokens')).toContainText('3');
  await expect(page.getByTestId('admin-etl-pii-privileged-excluded')).toContainText('1');
  await expect(page.getByTestId('admin-etl-audit-total')).toContainText('0');
  await expect(page.getByTestId('admin-etl-location-archive')).toContainText('dry-run');
  await expect(page.getByTestId('admin-etl-location-archive-total')).toContainText('1');
  await expect(page.getByTestId('admin-etl-location-archive-bridge')).toContainText('일치');
  await expect(page.getByTestId('admin-etl-location-archive-pending')).toContainText('0 / 1');
  await expect(page.getByTestId('admin-etl-location-purpose-nearby_attractions')).toContainText(
    '1',
  );
  await expect(page.getByTestId('admin-etl-kmap-dagster-status')).toContainText('정상');
  await expect(page.getByTestId('admin-etl-kmap-features')).toContainText('—');
  await expect(page.getByTestId('admin-etl-kmap-source-records')).toContainText('—');
  await expect(page.getByTestId('admin-etl-kmap-repositories')).toContainText('—');
  await expect(page.getByTestId('admin-etl-kmap-jobs')).toContainText('—');
  await expect(page.getByTestId('admin-etl-kmap-assets')).toContainText('—');
  await expect(page.getByTestId(`admin-etl-import-row-${jobId}`)).toBeVisible();
  await expect(page.getByTestId(`admin-etl-import-row-${jobId}`)).toContainText('1%');

  await page.getByTestId('admin-etl-import-status-filter').selectOption('failed');
  await expect(page.getByTestId(`admin-etl-import-row-${jobId}`)).toBeVisible();
  const lastUrl = new URL(seenJobUrls[seenJobUrls.length - 1]!);
  expect(lastUrl.searchParams.get('status')).toBe('failed');
});

test('Provider sync 페이지가 provider key와 job status 필터를 proxy query로 보낸다', async ({
  page,
}) => {
  const seenProviderUrls: string[] = [];
  const seenJobUrls: string[] = [];
  const seenCancelBodies: unknown[] = [];
  let reconciliationCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      seenProviderUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'unavailable',
            schedule_source_errors: ['Dagster GraphQL unavailable'],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      seenJobUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [importJob, ...cancellationOverlayJobs],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      seenCancelBodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 503,
        headers: {
          'Retry-After': '7',
          'Access-Control-Expose-Headers': 'Retry-After',
        },
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN',
            message: 'kor_travel_map import job cancel 서비스가 일시적으로 사용 불가합니다.',
            details: {
              status: 'in_progress',
              retryable: false,
              unresolved_member_count: 1,
              warnings: ['응답 유실로 취소 결과를 재조회해야 합니다.'],
            },
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      reconciliationCalls += 1;
      const status = reconciliationCalls === 1 ? 'in_progress' : 'retryable';
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            cancellation: {
              cancellation_id: cancellationId,
              status,
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'duplicate run',
              retryable: status === 'retryable',
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await expect(page.getByRole('heading', { name: 'Provider sync' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '재호출 가능' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '다음 예약' })).toBeVisible();
  await expect(page.getByTestId('admin-provider-row-kma-special_days-daily')).toBeVisible();
  await expect(page.getByTestId('admin-provider-schedule-source-warning')).toContainText(
    'Dagster GraphQL unavailable',
  );
  await expect(page.getByTestId(`admin-provider-job-row-${jobId}`)).toBeVisible();
  await expect(page.getByTestId(`admin-provider-job-row-${jobId}`)).toContainText('1%');
  await expect(
    page.getByTestId('admin-provider-job-cancel-55555555-5555-4555-8555-555555555555'),
  ).toBeDisabled();
  await expect(
    page.getByTestId('admin-provider-job-cancel-55555555-5555-4555-8555-555555555555'),
  ).toContainText('취소 진행 중');
  await expect(
    page.getByTestId('admin-provider-job-cancel-66666666-6666-4666-8666-666666666666'),
  ).toBeEnabled();
  await expect(
    page.getByTestId('admin-provider-job-cancel-66666666-6666-4666-8666-666666666666'),
  ).toContainText('취소 재시도');
  await expect(
    page.getByTestId('admin-provider-job-cancel-88888888-8888-4888-8888-888888888888'),
  ).toBeDisabled();
  await expect(
    page.getByTestId('admin-provider-job-cancel-99999999-9999-4999-8999-999999999999'),
  ).toBeDisabled();

  await page.getByTestId('admin-provider-sync-key').fill('kma');
  await page.getByTestId('admin-provider-sync-submit').click();
  await page.getByTestId('admin-provider-sync-job-status').selectOption('failed');
  await expect(page.getByTestId('admin-provider-row-kma-special_days-daily')).toBeVisible();

  const providerUrl = new URL(seenProviderUrls[seenProviderUrls.length - 1]!);
  const jobUrl = new URL(seenJobUrls[seenJobUrls.length - 1]!);
  expect(providerUrl.searchParams.get('key')).toBe('kma');
  expect(jobUrl.searchParams.get('status')).toBe('failed');

  await page.getByTestId('admin-provider-sync-job-status').selectOption('running');
  const providerCallsBeforeCancel = seenProviderUrls.length;
  const jobCallsBeforeCancel = seenJobUrls.length;
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toBeVisible();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('운영자가 중복 실행을 확인함');
  await page.getByTestId('admin-provider-job-cancel-map-reason').fill('duplicate run');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId('admin-provider-cancel-warning')).toContainText(
    'HTTP 503 · PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN',
  );
  await expect(page.getByTestId('admin-provider-cancel-warning')).toContainText(
    '7초 후 조회 가능',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeEnabled({
    timeout: 5_000,
  });
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '취소 재시도',
  );
  expect(reconciliationCalls).toBeGreaterThanOrEqual(2);
  expect(seenProviderUrls.length).toBeGreaterThan(providerCallsBeforeCancel);
  expect(seenJobUrls.length).toBeGreaterThan(jobCallsBeforeCancel);
  expect(seenCancelBodies).toEqual([
    {
      access_reason: '운영자가 중복 실행을 확인함',
      kor_travel_map_reason: 'duplicate run',
    },
  ]);
});

test('취소 422 거절은 polling과 행 잠금 없이 입력을 보존하고 재시도할 수 있다', async ({
  page,
}) => {
  let cancelCalls = 0;
  let detailCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      if (cancelCalls === 1) {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'VALIDATION_ERROR',
              message: '취소 사유 형식이 올바르지 않습니다.',
            },
          }),
        });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            requested_job_id: jobId,
            root_kind: 'import_job',
            root_id: jobId,
            cancellation_id: cancellationId,
            status: 'completed',
            requested_at: '2026-06-12T00:03:00+09:00',
            requested_by: 'service:pinvi',
            reason: '검증 오류 수정 후 재시도',
            retryable: false,
            unresolved_member_count: 0,
            warnings: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            status: 'cancelled',
            cancellation: {
              cancellation_id: cancellationId,
              status: 'completed',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: '검증 오류 수정 후 재시도',
              retryable: false,
              unresolved_member_count: 0,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  const reasonInput = page.getByTestId('admin-provider-job-cancel-reason');
  const mapReasonInput = page.getByTestId('admin-provider-job-cancel-map-reason');
  await expect(reasonInput).toHaveAttribute('maxlength', '500');
  await expect(mapReasonInput).toHaveAttribute('maxlength', '500');
  await reasonInput.fill('가'.repeat(500));
  await expect(page.getByTestId('admin-provider-job-cancel-reason-count')).toHaveText('500/500');
  await page.getByTestId('admin-provider-job-cancel-submit').click();

  await expect(page.getByTestId('admin-provider-sync-error')).toContainText(
    'HTTP 422 · VALIDATION_ERROR',
  );
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toBeVisible();
  await expect(reasonInput).toHaveValue('가'.repeat(500));
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeEnabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText('취소');
  await expect(page.getByTestId('admin-provider-cancel-warning')).toHaveCount(0);
  await page.waitForTimeout(2_200);
  expect(detailCalls).toBe(0);

  await reasonInput.fill('검증 오류 수정 후 재시도');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toHaveCount(0);
  await expect.poll(() => detailCalls).toBeGreaterThanOrEqual(1);
  expect(cancelCalls).toBe(2);
});

test('정확한 execution-not-found 404는 polling 없이 입력을 보존하고 재시도할 수 있다', async ({
  page,
}) => {
  let cancelCalls = 0;
  let detailCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'PIPELINE_EXECUTION_NOT_FOUND',
            message: '취소할 pipeline execution을 찾을 수 없습니다.',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: importJob }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  const reasonInput = page.getByTestId('admin-provider-job-cancel-reason');
  await reasonInput.fill('삭제된 execution 확인');
  await page.getByTestId('admin-provider-job-cancel-submit').click();

  await expect(page.getByTestId('admin-provider-sync-error')).toContainText(
    'HTTP 404 · PIPELINE_EXECUTION_NOT_FOUND',
  );
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toBeVisible();
  await expect(reasonInput).toHaveValue('삭제된 execution 확인');
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeEnabled();
  await expect(page.getByTestId('admin-provider-cancel-warning')).toHaveCount(0);
  await page.waitForTimeout(2_200);
  expect(detailCalls).toBe(0);

  await reasonInput.fill('목록 갱신 전 재확인');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect.poll(() => cancelCalls).toBe(2);
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toBeVisible();
  expect(detailCalls).toBe(0);
});

test('code가 다른 일반 404는 결과 미확정으로 잠그고 reconciliation한다', async ({ page }) => {
  let cancelCalls = 0;
  let detailCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'ROUTE_NOT_FOUND',
            message: '요청 경로를 찾을 수 없습니다.',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            cancellation: {
              cancellation_id: cancellationId,
              status: 'in_progress',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'route drift outcome check',
              retryable: false,
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('일반 404 결과 확인');
  await page.getByTestId('admin-provider-job-cancel-submit').click();

  await expect(page.getByTestId('admin-provider-cancel-warning')).toContainText(
    'HTTP 404 · ROUTE_NOT_FOUND',
  );
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toHaveCount(0);
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  expect(cancelCalls).toBe(1);
  await expect.poll(() => detailCalls).toBeGreaterThanOrEqual(2);
});

test('operator는 Provider 상태를 조회하지만 import job 취소 capability를 보지 못한다', async ({
  page,
}) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: { ...adminUser, roles: ['user', 'operator'], email: 'operator@example.com' },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await expect(page.getByTestId(`admin-provider-job-row-${jobId}`)).toBeVisible();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toHaveCount(0);
  await expect(page.getByTestId('admin-provider-job-cancel-panel')).toHaveCount(0);
});

test('취소 성공 뒤 stale 목록이 running이어도 fresh 상세 확인 전 guard를 해제하지 않는다', async ({
  page,
}) => {
  let providerCalls = 0;
  let listCalls = 0;
  let detailCalls = 0;
  let cancelCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      providerCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      listCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            requested_job_id: jobId,
            root_kind: 'import_job',
            root_id: jobId,
            cancellation_id: cancellationId,
            status: 'completed',
            requested_at: '2026-06-12T00:03:00+09:00',
            requested_by: 'service:pinvi',
            reason: 'duplicate run',
            retryable: false,
            unresolved_member_count: 0,
            warnings: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      const completed = detailCalls >= 2;
      if (completed) await new Promise((resolve) => setTimeout(resolve, 500));
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            status: completed ? 'cancelled' : 'running',
            cancellation: completed
              ? {
                  cancellation_id: cancellationId,
                  status: 'completed',
                  requested_at: '2026-06-12T00:03:00+09:00',
                  requested_by: 'service:pinvi',
                  reason: 'duplicate run',
                  retryable: false,
                  unresolved_member_count: 0,
                }
              : null,
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('성공 응답 뒤 stale window 검증');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText('취소 완료');
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  expect(cancelCalls).toBe(1);
  expect(detailCalls).toBeGreaterThanOrEqual(2);
  expect(providerCalls).toBeGreaterThanOrEqual(2);
  expect(listCalls).toBeGreaterThanOrEqual(2);
});

test('브라우저 응답 유실은 blind retry 없이 detail/list/grid reconciliation을 잠근다', async ({
  page,
}) => {
  let providerCalls = 0;
  let listCalls = 0;
  let detailCalls = 0;
  let cancelCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      providerCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      listCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.abort('failed');
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            cancellation: {
              cancellation_id: cancellationId,
              status: 'in_progress',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'transport lost',
              retryable: false,
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('응답 유실 blind retry 방지');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId('admin-provider-cancel-warning')).toContainText(
    '취소 요청 응답을 확인하지 못했습니다',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  expect(cancelCalls).toBe(1);
  await expect.poll(() => detailCalls).toBeGreaterThanOrEqual(2);
  expect(providerCalls).toBeGreaterThanOrEqual(2);
  expect(listCalls).toBeGreaterThanOrEqual(2);
});

test('Pinvi 감사 실패 500도 terminal로 오인하지 않고 reconciliation을 잠근다', async ({
  page,
}) => {
  let providerCalls = 0;
  let listCalls = 0;
  let detailCalls = 0;
  let cancelCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      providerCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      listCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [importJob], page_size: 50, next_cursor: null } }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'INTERNAL_ERROR',
            message: '취소 결과 감사 기록을 완료하지 못했습니다.',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      detailCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            cancellation: {
              cancellation_id: cancellationId,
              status: 'in_progress',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'audit result lost',
              retryable: false,
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('감사 실패 뒤 blind retry 방지');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId('admin-provider-cancel-warning')).toContainText(
    'HTTP 500 · INTERNAL_ERROR',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  expect(cancelCalls).toBe(1);
  await expect.poll(() => detailCalls).toBeGreaterThanOrEqual(2);
  expect(providerCalls).toBeGreaterThanOrEqual(2);
  expect(listCalls).toBeGreaterThanOrEqual(2);
});

test('취소 reconciliation은 해당 job 행만 잠근다', async ({ page }) => {
  const otherJobId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  const otherJob = {
    ...importJob,
    job_id: otherJobId,
    projected_job_id: otherJobId,
    status_url: `/v1/ops/pipeline/executions/import_job/${otherJobId}`,
  };
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: { items: [importJob, otherJob], page_size: 50, next_cursor: null },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}/cancel`,
    async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN',
            message: '취소 결과를 확인해야 합니다.',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${jobId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...importJob,
            cancellation: {
              cancellation_id: cancellationId,
              status: 'in_progress',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'row-local guard',
              retryable: false,
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${otherJobId}/cancel`,
    async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN',
            message: '두 번째 취소 결과도 확인해야 합니다.',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${otherJobId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...otherJob,
            cancellation: {
              cancellation_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
              status: 'retryable',
              requested_at: '2026-06-12T00:04:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'second row guard',
              retryable: true,
              unresolved_member_count: 1,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await page.getByTestId(`admin-provider-job-cancel-${jobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('행 단위 잠금 검증');
  await page.getByTestId('admin-provider-job-cancel-submit').click();

  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${otherJobId}`)).toBeEnabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${otherJobId}`)).toContainText('취소');

  await page.getByTestId(`admin-provider-job-cancel-${otherJobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('두 번째 행 잠금 검증');
  await page.getByTestId('admin-provider-job-cancel-submit').click();

  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  await expect(page.getByTestId(`admin-provider-job-cancel-${otherJobId}`)).toBeEnabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${otherJobId}`)).toContainText(
    '취소 재시도',
  );
  const firstMessage = page.locator(`[data-reconciliation-job-id="${jobId}"]`);
  const secondMessage = page.locator(`[data-reconciliation-job-id="${otherJobId}"]`);
  await expect(firstMessage).not.toContainText('retryable 상태가 확인되어');
  await expect(secondMessage).toContainText('retryable 상태가 확인되어');
});

test('job status 전환 placeholder에서는 stale 행 취소를 잠근다', async ({ page }) => {
  let releaseFailedStatus: (() => void) | undefined;
  const failedStatusGate = new Promise<void>((resolve) => {
    releaseFailedStatus = resolve;
  });
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      const status = new URL(route.request().url()).searchParams.get('status');
      if (status === 'failed') await failedStatusGate;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: status === 'failed' ? [] : [importJob],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeEnabled();
  await page.getByTestId('admin-provider-sync-job-status').selectOption('failed');
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toBeDisabled();
  await expect(page.getByTestId(`admin-provider-job-cancel-${jobId}`)).toContainText(
    '상태 확인 중',
  );
  releaseFailedStatus?.();
  await expect(page.getByTestId(`admin-provider-job-row-${jobId}`)).not.toBeVisible();
});

test('cursor 페이지네이션으로 50개 이후 job도 조회하고 취소한다', async ({ page }) => {
  const lateJobId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
  const firstPageJobs = Array.from({ length: 50 }, (_, index) => {
    const id = `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`;
    return {
      ...importJob,
      job_id: id,
      projected_job_id: id,
      status_url: `/v1/ops/pipeline/executions/import_job/${id}`,
    };
  });
  const lateJob = {
    ...importJob,
    job_id: lateJobId,
    projected_job_id: lateJobId,
    status_url: `/v1/ops/pipeline/executions/import_job/${lateJobId}`,
  };
  const seenCursors: Array<string | null> = [];
  let releaseSecondPage: (() => void) | undefined;
  const secondPageGate = new Promise<void>((resolve) => {
    releaseSecondPage = resolve;
  });
  let cancelCalls = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: [provider],
            total: 1,
            schedule_source_status: 'ok',
            schedule_source_errors: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/provider-sync/import-jobs',
    async (route) => {
      const cursor = new URL(route.request().url()).searchParams.get('cursor');
      seenCursors.push(cursor);
      if (cursor === 'cursor-2') await secondPageGate;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            items: cursor === 'cursor-2' ? [lateJob] : firstPageJobs,
            page_size: 50,
            next_cursor: cursor === 'cursor-2' ? null : 'cursor-2',
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${lateJobId}/cancel`,
    async (route) => {
      cancelCalls += 1;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            requested_job_id: lateJobId,
            root_kind: 'import_job',
            root_id: lateJobId,
            cancellation_id: cancellationId,
            status: 'completed',
            requested_at: '2026-06-12T00:03:00+09:00',
            requested_by: 'service:pinvi',
            reason: 'late page cancel',
            retryable: false,
            unresolved_member_count: 0,
            warnings: [],
          },
        }),
      });
    },
  );
  await page.route(
    (url) =>
      url.port === '12801' &&
      url.pathname === `/admin/provider-sync/import-jobs/${lateJobId}`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...lateJob,
            status: 'cancelled',
            cancellation: {
              cancellation_id: cancellationId,
              status: 'completed',
              requested_at: '2026-06-12T00:03:00+09:00',
              requested_by: 'service:pinvi',
              reason: 'late page cancel',
              retryable: false,
              unresolved_member_count: 0,
            },
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await expect(page.getByTestId('admin-provider-jobs-page')).toContainText('1 페이지');
  await page.getByTestId('admin-provider-jobs-next').click();
  await expect(page.getByTestId('admin-provider-jobs-next')).toBeDisabled();
  await expect(page.getByTestId('admin-provider-jobs-prev')).toBeDisabled();
  await expect(
    page.getByTestId(`admin-provider-job-cancel-${firstPageJobs[0]!.job_id}`),
  ).toBeDisabled();
  releaseSecondPage?.();
  await expect(page.getByTestId('admin-provider-jobs-page')).toContainText('2 페이지');
  await expect(page.getByTestId(`admin-provider-job-row-${lateJobId}`)).toBeVisible();
  expect(seenCursors.filter((cursor) => cursor === 'cursor-2')).toHaveLength(1);

  await page.getByTestId(`admin-provider-job-cancel-${lateJobId}`).click();
  await page.getByTestId('admin-provider-job-cancel-reason').fill('50개 이후 job 취소 검증');
  await page.getByTestId('admin-provider-job-cancel-submit').click();
  await expect(page.getByTestId('admin-provider-sync-mutation-notice')).toContainText(lateJobId);
  expect(cancelCalls).toBe(1);

  await page.getByTestId('admin-provider-jobs-prev').click();
  await expect(page.getByTestId('admin-provider-jobs-page')).toContainText('1 페이지');
});
