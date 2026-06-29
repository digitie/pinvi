'use client';

import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminProviderImportJobListParams,
} from '@pinvi/api-client';
import type {
  AdminDagsterRunSummary,
  AdminEmailOutboxTemplateSummary,
  AdminProviderImportJobRecord,
  AdminTelegramOutboxCategorySummary,
} from '@pinvi/schemas';
import {
  Activity,
  Archive,
  Bell,
  Database,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from 'lucide-react';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const IMPORT_JOB_STATUS_OPTIONS = [
  { value: 'all', label: '전체' },
  { value: 'queued', label: '대기' },
  { value: 'running', label: '실행 중' },
  { value: 'done', label: '완료' },
  { value: 'failed', label: '실패' },
  { value: 'cancelled', label: '취소' },
] as const;

const STATUS_LABEL: Record<string, string> = {
  queued: '대기',
  running: '실행 중',
  done: '완료',
  failed: '실패',
  cancelled: '취소',
  ok: '정상',
  degraded: '주의',
  down: '중단',
  unknown: '미확인',
  unavailable: '미가용',
  error: '오류',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function formatUnixTime(value: number | null | undefined) {
  return typeof value === 'number' ? new Date(value * 1000).toLocaleString('ko-KR') : '—';
}

function statusLabel(value: string | null | undefined) {
  return value ? (STATUS_LABEL[value] ?? value) : '—';
}

function formatMetric(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString('ko-KR') : '—';
}

function progressLabel(value: number | null | undefined) {
  if (typeof value !== 'number') return '—';
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function percentLabel(value: number | null | undefined) {
  if (typeof value !== 'number') return '—';
  return `${Math.round(value * 1000) / 10}%`;
}

function EmailTemplateStat({ item }: { item: AdminEmailOutboxTemplateSummary }) {
  return (
    <li
      key={item.template}
      className="rounded-sm bg-surface-soft p-2"
      data-testid={`admin-etl-email-template-${item.template}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs">{item.template}</span>
        <span className="text-xs text-muted">{percentLabel(item.failure_rate)}</span>
      </div>
      <div className="mt-1 text-xs text-muted">
        total {formatMetric(item.total)} / failed {formatMetric(item.failure_count)}
      </div>
    </li>
  );
}

function TelegramCategoryStat({ item }: { item: AdminTelegramOutboxCategorySummary }) {
  return (
    <li
      key={item.category}
      className="rounded-sm bg-surface-soft p-2"
      data-testid={`admin-etl-telegram-category-${item.category}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-xs">{item.category}</span>
        <span className="text-xs text-muted">{percentLabel(item.retry_exhausted_rate)}</span>
      </div>
      <div className="mt-1 text-xs text-muted">
        total {formatMetric(item.total)} / retry exhausted {formatMetric(item.retry_exhausted)}
      </div>
    </li>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
      {message}
    </p>
  );
}

export default function AdminEtlPage() {
  const [statusFilter, setStatusFilter] =
    useState<(typeof IMPORT_JOB_STATUS_OPTIONS)[number]['value']>('running');

  const importJobParams = useMemo<AdminProviderImportJobListParams>(
    () => ({
      status: statusFilter === 'all' ? undefined : statusFilter,
      pageSize: 50,
    }),
    [statusFilter],
  );

  const summaryQuery = useQuery({
    queryKey: queryKeys.admin.etlSummary(),
    queryFn: () => adminApi(apiClient).getEtlSummary(),
  });

  const jobsQuery = useQuery({
    queryKey: queryKeys.admin.providerImportJobs(importJobParams),
    queryFn: () => adminApi(apiClient).listProviderImportJobs(importJobParams),
    placeholderData: keepPreviousData,
  });

  const summary = summaryQuery.data ?? null;
  const importJobs = jobsQuery.data?.items ?? [];
  const emailOutbox = summary?.pinvi.email_outbox ?? null;
  const telegramOutbox = summary?.pinvi.telegram_outbox ?? null;
  const piiRetention = summary?.pinvi.pii_retention ?? null;
  const locationArchive = summary?.pinvi.location_log_archive ?? null;
  const pinviRepositories = useMemo(
    () => summary?.pinvi.repositories ?? [],
    [summary?.pinvi.repositories],
  );
  const pinviRecentRuns = useMemo(
    () => summary?.pinvi.recent_runs ?? [],
    [summary?.pinvi.recent_runs],
  );
  const liveJobNames = useMemo(() => {
    return new Set(
      pinviRepositories.flatMap((repository) => repository.jobs.map((job) => job.name)),
    );
  }, [pinviRepositories]);
  const liveScheduleByJobName = useMemo(() => {
    const schedules = new Map<
      string,
      {
        name: string;
        cron_schedule: string | null;
        execution_timezone: string | null;
        status: string | null;
      }
    >();
    for (const repository of pinviRepositories) {
      for (const schedule of repository.schedules) {
        if (schedule.job_name) schedules.set(schedule.job_name, schedule);
      }
    }
    return schedules;
  }, [pinviRepositories]);
  const latestRunByJobName = useMemo(() => {
    const runs = new Map<string, AdminDagsterRunSummary>();
    for (const run of pinviRecentRuns) {
      if (run.job_name && !runs.has(run.job_name)) runs.set(run.job_name, run);
    }
    return runs;
  }, [pinviRecentRuns]);

  const summaryError = summaryQuery.isError
    ? summaryQuery.error instanceof ApiError
      ? summaryQuery.error.message
      : 'ETL 요약 조회에 실패했습니다.'
    : null;
  const jobsError = jobsQuery.isError
    ? jobsQuery.error instanceof ApiError
      ? jobsQuery.error.message
      : 'import job 조회에 실패했습니다.'
    : null;

  const columns: AdminTableColumn<AdminProviderImportJobRecord>[] = [
    {
      key: 'job',
      header: 'job',
      sortable: true,
      sortValue: (item) => item.job_id,
      cell: (item) => (
        <div>
          <div className="break-all font-mono text-xs">{item.job_id}</div>
          <div className="text-xs text-muted">{item.kind}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => statusLabel(item.status),
    },
    {
      key: 'progress',
      header: '진행',
      sortable: true,
      sortValue: (item) => item.progress ?? 0,
      cell: (item) => progressLabel(item.progress),
      align: 'right',
    },
    {
      key: 'stage',
      header: 'stage',
      sortable: true,
      sortValue: (item) => item.current_stage ?? '',
      cell: (item) => item.current_stage ?? '—',
    },
    {
      key: 'created_at',
      header: '생성',
      sortable: true,
      sortValue: (item) => new Date(item.created_at).getTime(),
      cell: (item) => formatDateTime(item.created_at),
    },
    {
      key: 'finished_at',
      header: '완료',
      sortable: true,
      sortValue: (item) => (item.finished_at ? new Date(item.finished_at).getTime() : 0),
      cell: (item) => formatDateTime(item.finished_at),
    },
  ];

  return (
    <AdminPage
      title="ETL"
      description="Pinvi app ETL 정의와 kor-travel-map provider ETL 실행 상태"
      actions={
        <button
          type="button"
          onClick={() => {
            void summaryQuery.refetch();
            void jobsQuery.refetch();
          }}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-etl-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      <FilterBar>
        <label htmlFor="admin-etl-import-status-filter" className="text-xs text-muted">
          import job 상태
        </label>
        <select
          id="admin-etl-import-status-filter"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
          className={inputClass}
          data-testid="admin-etl-import-status-filter"
        >
          {IMPORT_JOB_STATUS_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">
          {summary?.generated_at ? `요약 ${formatDateTime(summary.generated_at)}` : '요약 대기'}
        </span>
      </FilterBar>

      {summaryError && <ErrorBox message={summaryError} />}

      <div className="grid gap-4 xl:grid-cols-2">
        <Section title="Pinvi Dagster">
          <div className="grid gap-3 text-sm sm:grid-cols-5">
            <div data-testid="admin-etl-pinvi-status">
              <div className="text-xs text-muted">상태</div>
              <div className="font-semibold">{statusLabel(summary?.pinvi.status)}</div>
              <div className="text-xs text-muted">{summary?.pinvi.message ?? '—'}</div>
            </div>
            <div data-testid="admin-etl-pinvi-live-repository-count">
              <div className="text-xs text-muted">code locations</div>
              <div className="font-semibold">{formatMetric(summary?.pinvi.repository_count)}</div>
            </div>
            <div data-testid="admin-etl-pinvi-live-asset-count">
              <div className="text-xs text-muted">live assets</div>
              <div className="font-semibold">{formatMetric(summary?.pinvi.asset_count)}</div>
            </div>
            <div data-testid="admin-etl-pinvi-live-job-count">
              <div className="text-xs text-muted">live jobs</div>
              <div className="font-semibold">{formatMetric(summary?.pinvi.job_count)}</div>
            </div>
            <div data-testid="admin-etl-pinvi-live-schedule-count">
              <div className="text-xs text-muted">schedules</div>
              <div className="font-semibold">{formatMetric(summary?.pinvi.schedule_count)}</div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <Database className="h-3.5 w-3.5" aria-hidden="true" />
                Assets
              </h3>
              <ul className="space-y-2 text-sm">
                {(summary?.pinvi.assets ?? []).map((asset) => (
                  <li key={asset.key} className="rounded-sm bg-surface-soft p-2">
                    <div className="font-mono text-xs">{asset.key}</div>
                    <div className="text-xs text-muted">{asset.description ?? '—'}</div>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <Workflow className="h-3.5 w-3.5" aria-hidden="true" />
                Jobs
              </h3>
              <ul className="space-y-2 text-sm">
                {(summary?.pinvi.jobs ?? []).map((job) => (
                  <li
                    key={job.name}
                    className="rounded-sm bg-surface-soft p-2"
                    data-testid={`admin-etl-job-${job.name}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-xs">{job.name}</span>
                      <span
                        className="text-xs text-muted"
                        data-testid={`admin-etl-job-${job.name}-live`}
                      >
                        {liveJobNames.has(job.name) ? 'live' : 'registry'}
                      </span>
                    </div>
                    <div className="text-xs text-muted">
                      {job.trigger} / {job.description ?? '—'}
                    </div>
                    <div className="mt-2 grid gap-2 text-xs text-muted sm:grid-cols-3">
                      <span>
                        schedule{' '}
                        {liveScheduleByJobName.get(job.name)?.cron_schedule ??
                          summary?.pinvi.schedules.find((item) => item.job_name === job.name)
                            ?.cron_schedule ??
                          '—'}
                      </span>
                      <span data-testid={`admin-etl-job-${job.name}-timezone`}>
                        {liveScheduleByJobName.get(job.name)?.execution_timezone ??
                          summary?.pinvi.schedules.find((item) => item.job_name === job.name)
                            ?.execution_timezone ??
                          '—'}
                      </span>
                      <span data-testid={`admin-etl-job-${job.name}-latest-run`}>
                        {statusLabel(latestRunByJobName.get(job.name)?.status)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {pinviRepositories.length ? (
            <div className="mt-4" data-testid="admin-etl-pinvi-live-repositories">
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
                Live code locations
              </h3>
              <ul className="space-y-2 text-sm">
                {pinviRepositories.map((repository) => (
                  <li
                    key={`${repository.location_name ?? 'unknown'}-${repository.name}`}
                    className="rounded-sm bg-surface-soft p-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-xs">{repository.name}</span>
                      <span className="text-xs text-muted">{repository.location_name ?? '—'}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      jobs {formatMetric(repository.jobs.length)} / assets{' '}
                      {formatMetric(repository.asset_count)} / schedules{' '}
                      {formatMetric(repository.schedules.length)}
                    </div>
                    {repository.asset_groups.length ? (
                      <div className="mt-1 text-xs text-muted">
                        {repository.asset_groups.join(', ')}
                      </div>
                    ) : null}
                    {repository.schedules.length ? (
                      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                        {repository.schedules.map((schedule) => (
                          <li
                            key={schedule.name}
                            className="rounded-sm border border-hairline px-2 py-1 text-xs"
                            data-testid={`admin-etl-pinvi-live-schedule-${schedule.name}`}
                          >
                            <span className="font-mono">{schedule.name}</span>
                            <span className="ml-2 text-muted">
                              {schedule.execution_timezone ?? '—'} / {statusLabel(schedule.status)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {pinviRecentRuns.length ? (
            <div className="mt-4" data-testid="admin-etl-pinvi-live-runs">
              <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <Activity className="h-3.5 w-3.5" aria-hidden="true" />
                Recent Pinvi runs
              </h3>
              <ul className="space-y-2 text-sm">
                {pinviRecentRuns.map((run) => (
                  <li key={run.run_id} className="rounded-sm bg-surface-soft p-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-xs">{run.job_name ?? run.run_id}</span>
                      <span className="text-xs text-muted">{statusLabel(run.status)}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {formatUnixTime(run.start_time)} → {formatUnixTime(run.end_time)}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {emailOutbox ? (
            <div
              className="mt-4 rounded-sm border border-hairline p-3"
              data-testid="admin-etl-email-outbox"
            >
              <h3 className="mb-3 text-xs font-semibold uppercase text-muted">Email outbox</h3>
              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div>
                  <div className="text-xs text-muted">due</div>
                  <div className="font-semibold">{formatMetric(emailOutbox.pending_due)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">backoff</div>
                  <div className="font-semibold">{formatMetric(emailOutbox.pending_backoff)}</div>
                </div>
                <div data-testid="admin-etl-email-stuck">
                  <div className="text-xs text-muted">stuck</div>
                  <div className="font-semibold">{formatMetric(emailOutbox.stuck_pending)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">retry exhausted</div>
                  <div className="font-semibold">{formatMetric(emailOutbox.retry_exhausted)}</div>
                </div>
              </div>
              <div className="mt-2 text-xs text-muted">
                threshold {emailOutbox.stuck_threshold_minutes}m / max attempts{' '}
                {emailOutbox.max_attempts} / {emailOutbox.template_window_hours}h templates
              </div>
              {emailOutbox.template_stats.length ? (
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {emailOutbox.template_stats.map((item) => (
                    <EmailTemplateStat key={item.template} item={item} />
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          {telegramOutbox ? (
            <div
              className="mt-4 rounded-sm border border-hairline p-3"
              data-testid="admin-etl-telegram-outbox"
            >
              <h3 className="mb-3 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <Bell className="h-3.5 w-3.5" aria-hidden="true" />
                Telegram outbox
              </h3>
              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div>
                  <div className="text-xs text-muted">due</div>
                  <div className="font-semibold">{formatMetric(telegramOutbox.pending_due)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">backoff</div>
                  <div className="font-semibold">
                    {formatMetric(telegramOutbox.pending_backoff)}
                  </div>
                </div>
                <div data-testid="admin-etl-telegram-stuck">
                  <div className="text-xs text-muted">stuck</div>
                  <div className="font-semibold">{formatMetric(telegramOutbox.stuck_pending)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">retry exhausted</div>
                  <div className="font-semibold">
                    {formatMetric(telegramOutbox.retry_exhausted)}
                  </div>
                </div>
              </div>
              <div className="mt-3 grid gap-3 text-xs text-muted sm:grid-cols-3">
                <div>sent {formatMetric(telegramOutbox.sent)}</div>
                <div>skipped {formatMetric(telegramOutbox.skipped)}</div>
                <div>failed {formatMetric(telegramOutbox.failed)}</div>
              </div>
              <div className="mt-2 text-xs text-muted">
                threshold {telegramOutbox.stuck_threshold_minutes}m / max attempts{' '}
                {telegramOutbox.max_attempts} / {telegramOutbox.category_window_hours}h categories
              </div>
              {telegramOutbox.category_stats.length ? (
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {telegramOutbox.category_stats.map((item) => (
                    <TelegramCategoryStat key={item.category} item={item} />
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          {piiRetention ? (
            <div
              className="mt-4 rounded-sm border border-hairline p-3"
              data-testid="admin-etl-pii-retention"
            >
              <h3 className="mb-3 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                PII retention
              </h3>
              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div data-testid="admin-etl-pii-total">
                  <div className="text-xs text-muted">candidates</div>
                  <div className="font-semibold">{formatMetric(piiRetention.total_candidates)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted">deleted users</div>
                  <div className="font-semibold">
                    {formatMetric(piiRetention.deleted_user_pii_candidates)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">sessions</div>
                  <div className="font-semibold">
                    {formatMetric(
                      piiRetention.old_revoked_sessions + piiRetention.old_expired_sessions,
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">location logs</div>
                  <div className="font-semibold">
                    {formatMetric(piiRetention.location_access_logs_over_retention)}
                  </div>
                </div>
              </div>
              <div className="mt-3 grid gap-3 text-xs text-muted sm:grid-cols-3">
                <div data-testid="admin-etl-pii-tokens">
                  tokens{' '}
                  {formatMetric(
                    piiRetention.expired_signup_verifications +
                      piiRetention.expired_password_reset_tokens,
                  )}
                </div>
                <div>
                  OAuth{' '}
                  {formatMetric(
                    piiRetention.expired_oauth_login_states +
                      piiRetention.expired_mobile_oauth_exchanges,
                  )}
                </div>
                <div data-testid="admin-etl-pii-privileged-excluded">
                  privileged excluded {formatMetric(piiRetention.excluded_privileged_deleted_users)}
                </div>
              </div>
              <div className="mt-2 text-xs text-muted">
                dry-run / user {piiRetention.user_pii_grace_days}d / session{' '}
                {piiRetention.session_grace_days}d / location{' '}
                {piiRetention.location_retention_months}mo
              </div>
            </div>
          ) : null}
          {locationArchive ? (
            <div
              className="mt-4 rounded-sm border border-hairline p-3"
              data-testid="admin-etl-location-archive"
            >
              <h3 className="mb-3 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
                <Archive className="h-3.5 w-3.5" aria-hidden="true" />
                Location log archive
              </h3>
              <div className="grid gap-3 text-sm sm:grid-cols-4">
                <div data-testid="admin-etl-location-archive-total">
                  <div className="text-xs text-muted">candidates</div>
                  <div className="font-semibold">
                    {formatMetric(locationArchive.total_candidates)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted">active rows</div>
                  <div className="font-semibold">
                    {formatMetric(locationArchive.active_rows_after_cutoff)}
                  </div>
                </div>
                <div data-testid="admin-etl-location-archive-pending">
                  <div className="text-xs text-muted">pending outbox</div>
                  <div className="font-semibold">
                    {formatMetric(locationArchive.pending_outbox_before_cutoff)} /{' '}
                    {formatMetric(locationArchive.pending_outbox_total)}
                  </div>
                </div>
                <div data-testid="admin-etl-location-archive-bridge">
                  <div className="text-xs text-muted">chain bridge</div>
                  <div className="font-semibold">
                    {locationArchive.chain_bridge_required
                      ? locationArchive.bridge_anchor_matches
                        ? '일치'
                        : '불일치'
                      : '불필요'}
                  </div>
                </div>
              </div>
              <div className="mt-3 grid gap-3 text-xs text-muted sm:grid-cols-3">
                <div>cutoff {formatDateTime(locationArchive.archive_cutoff)}</div>
                <div>tail {locationArchive.archive_tail_log_id ?? '—'}</div>
                <div>head {locationArchive.active_head_log_id ?? '—'}</div>
              </div>
              {locationArchive.purpose_stats.length ? (
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {locationArchive.purpose_stats.map((item) => (
                    <li
                      key={item.purpose}
                      className="rounded-sm bg-surface-soft p-2 text-xs"
                      data-testid={`admin-etl-location-purpose-${item.purpose}`}
                    >
                      <span className="font-mono">{item.purpose}</span>
                      <span className="ml-2 text-muted">{formatMetric(item.total)}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="mt-2 text-xs text-muted">
                dry-run / retention {locationArchive.location_retention_months}mo / blocked{' '}
                {locationArchive.archive_blocked_by_pending_outbox ? 'yes' : 'no'}
              </div>
            </div>
          ) : null}
          <div className="mt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted">Schedules</h3>
            <ul className="space-y-2 text-sm">
              {(summary?.pinvi.schedules ?? []).map((schedule) => (
                <li key={schedule.name} className="rounded-sm bg-surface-soft p-2">
                  <span className="font-mono text-xs">{schedule.name}</span>
                  <span className="ml-2 text-xs text-muted">
                    {schedule.cron_schedule} / {schedule.execution_timezone ?? '—'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Section>

        <Section title="kor-travel-map Dagster">
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div data-testid="admin-etl-kmap-dagster-status">
              <div className="text-xs text-muted">Dagster</div>
              <div className="font-semibold">
                {statusLabel(summary?.kor_travel_map.dagster_status)}
              </div>
              <div className="text-xs text-muted">
                {statusLabel(summary?.kor_travel_map.status)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">features</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.features_total)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">providers</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.provider_dataset_count)}
              </div>
            </div>
          </div>
          <div className="mt-4 grid gap-3 text-sm sm:grid-cols-5">
            <div>
              <div className="text-xs text-muted">repositories</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.repository_count)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">jobs</div>
              <div className="font-semibold">{formatMetric(summary?.kor_travel_map.job_count)}</div>
            </div>
            <div>
              <div className="text-xs text-muted">assets</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.asset_count)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">schedules</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.schedule_count)}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">failures</div>
              <div className="font-semibold">
                {formatMetric(summary?.kor_travel_map.provider_failure_count)}
              </div>
            </div>
          </div>
          {summary?.kor_travel_map.errors.length ? (
            <ul className="mt-4 space-y-1 text-xs text-error-text">
              {summary.kor_travel_map.errors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-4">
            <h3 className="mb-2 flex items-center gap-1 text-xs font-semibold uppercase text-muted">
              <GitBranch className="h-3.5 w-3.5" aria-hidden="true" />
              Recent runs
            </h3>
            <ul className="space-y-2 text-sm">
              {(summary?.kor_travel_map.recent_runs ?? []).slice(0, 5).map((run) => (
                <li key={run.run_id} className="rounded-sm bg-surface-soft p-2">
                  <div className="font-mono text-xs">{run.job_name ?? run.run_id}</div>
                  <div className="text-xs text-muted">{statusLabel(run.status)}</div>
                </li>
              ))}
            </ul>
          </div>
        </Section>
      </div>

      {jobsError && <ErrorBox message={jobsError} />}

      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-muted">
          <Activity className="h-4 w-4" aria-hidden="true" />
          Provider import jobs
        </h2>
        <AdminTable
          columns={columns}
          rows={importJobs}
          loading={jobsQuery.isLoading}
          rowKey={(item) => item.job_id}
          rowTestId={(item) => `admin-etl-import-row-${item.job_id}`}
          empty="조회된 import job이 없습니다."
        />
      </section>
    </AdminPage>
  );
}
