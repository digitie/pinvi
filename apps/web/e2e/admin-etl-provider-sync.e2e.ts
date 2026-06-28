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

const importJob = {
  job_id: 'job-1',
  kind: 'provider_import',
  status: 'running',
  progress: 0.5,
  payload: { provider: 'kma' },
  status_url: '/v1/ops/import-jobs/job-1',
  current_stage: 'normalize',
  error_message: null,
  created_at: '2026-06-12T00:00:00+09:00',
  started_at: '2026-06-12T00:01:00+09:00',
  heartbeat_at: '2026-06-12T00:02:00+09:00',
  finished_at: null,
  load_batch_id: null,
  parent_job_id: null,
  source_checksum: null,
  links: {},
};

const provider = {
  provider: 'kma',
  dataset_key: 'special_days',
  sync_scope: 'daily',
  status: 'healthy',
  last_success_at: '2026-06-12T00:00:00+09:00',
  last_failure_at: null,
  consecutive_failures: 0,
  next_run_after: '2026-06-13T03:30:00+09:00',
  links: {},
  refresh_policy: { enabled: true },
};

const etlSummary = {
  generated_at: '2026-06-12T00:03:00+09:00',
  pinvi: {
    status: 'ok',
    message: 'Dagster 응답 정상',
    latency_ms: 10,
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
    pii_retention: {
      dry_run: true,
      generated_at: '2026-06-12T00:03:00+09:00',
      user_pii_cutoff: '2026-05-13T00:03:00+09:00',
      session_cutoff: '2026-05-13T00:03:00+09:00',
      location_cutoff: '2025-12-12T00:03:00+09:00',
      user_pii_grace_days: 30,
      session_grace_days: 30,
      location_retention_months: 6,
      total_candidates: 11,
      deleted_user_pii_candidates: 2,
      deleted_user_oauth_identity_candidates: 1,
      excluded_privileged_deleted_users: 1,
      expired_signup_verifications: 2,
      expired_password_reset_tokens: 1,
      old_revoked_sessions: 1,
      old_expired_sessions: 1,
      expired_oauth_login_states: 1,
      expired_mobile_oauth_exchanges: 1,
      location_access_logs_over_retention: 1,
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
    repository_count: 1,
    job_count: 3,
    asset_count: 8,
    schedule_count: 2,
    sensor_count: 0,
    run_counts: { STARTED: 1 },
    repositories: [],
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
    features_total: 42,
    source_records_total: 77,
    import_jobs_by_status: { running: 1 },
    dedup_queue_by_status: { pending: 2 },
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
  await expect(page.getByTestId('admin-etl-job-kasi_special_days_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-kasi_poi_rise_set_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_email_outbox_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_pii_retention_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-job-pinvi_location_log_archive_job')).toBeVisible();
  await expect(page.getByTestId('admin-etl-email-outbox')).toContainText('backoff');
  await expect(page.getByTestId('admin-etl-email-stuck')).toContainText('1');
  await expect(page.getByTestId('admin-etl-email-template-verify_email')).toContainText('33.3%');
  await expect(page.getByTestId('admin-etl-pii-retention')).toContainText('dry-run');
  await expect(page.getByTestId('admin-etl-pii-total')).toContainText('11');
  await expect(page.getByTestId('admin-etl-pii-tokens')).toContainText('3');
  await expect(page.getByTestId('admin-etl-pii-privileged-excluded')).toContainText('1');
  await expect(page.getByTestId('admin-etl-location-archive')).toContainText('dry-run');
  await expect(page.getByTestId('admin-etl-location-archive-total')).toContainText('1');
  await expect(page.getByTestId('admin-etl-location-archive-bridge')).toContainText('일치');
  await expect(page.getByTestId('admin-etl-location-archive-pending')).toContainText('0 / 1');
  await expect(page.getByTestId('admin-etl-location-purpose-nearby_attractions')).toContainText(
    '1',
  );
  await expect(page.getByTestId('admin-etl-kmap-dagster-status')).toContainText('정상');
  await expect(page.getByTestId('admin-etl-import-row-job-1')).toBeVisible();

  await page.getByTestId('admin-etl-import-status-filter').selectOption('failed');
  await expect(page.getByTestId('admin-etl-import-row-job-1')).toBeVisible();
  const lastUrl = new URL(seenJobUrls[seenJobUrls.length - 1]!);
  expect(lastUrl.searchParams.get('status')).toBe('failed');
});

test('Provider sync 페이지가 provider key와 job status 필터를 proxy query로 보낸다', async ({
  page,
}) => {
  const seenProviderUrls: string[] = [];
  const seenJobUrls: string[] = [];
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
            items: [importJob],
            page_size: 50,
            next_cursor: null,
          },
        }),
      });
    },
  );

  await page.goto('/admin/provider-sync');
  await expect(page.getByRole('heading', { name: 'Provider sync' })).toBeVisible();
  await expect(page.getByTestId('admin-provider-row-kma-special_days')).toBeVisible();
  await expect(page.getByTestId('admin-provider-job-row-job-1')).toBeVisible();

  await page.getByTestId('admin-provider-sync-key').fill('kma');
  await page.getByTestId('admin-provider-sync-submit').click();
  await page.getByTestId('admin-provider-sync-job-status').selectOption('failed');
  await expect(page.getByTestId('admin-provider-row-kma-special_days')).toBeVisible();

  const providerUrl = new URL(seenProviderUrls[seenProviderUrls.length - 1]!);
  const jobUrl = new URL(seenJobUrls[seenJobUrls.length - 1]!);
  expect(providerUrl.searchParams.get('key')).toBe('kma');
  expect(jobUrl.searchParams.get('status')).toBe('failed');
});
