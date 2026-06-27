'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminProviderImportJobListParams,
  type AdminProviderSyncListParams,
} from '@pinvi/api-client';
import type { AdminProviderDatasetSummary, AdminProviderImportJobRecord } from '@pinvi/schemas';
import { RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const IMPORT_JOB_STATUS_OPTIONS = [
  { value: 'all', label: 'job 전체' },
  { value: 'queued', label: '대기' },
  { value: 'running', label: '실행 중' },
  { value: 'done', label: '완료' },
  { value: 'failed', label: '실패' },
  { value: 'cancelled', label: '취소' },
] as const;

const STATUS_LABEL: Record<string, string> = {
  healthy: '정상',
  stale: '지연',
  failed: '실패',
  disabled: '중지',
  queued: '대기',
  running: '실행 중',
  done: '완료',
  cancelled: '취소',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function statusLabel(value: string | null | undefined) {
  return value ? (STATUS_LABEL[value] ?? value) : '—';
}

function progressLabel(value: number | null | undefined) {
  if (typeof value !== 'number') return '—';
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
      data-testid="admin-provider-sync-error"
    >
      {message}
    </p>
  );
}

export default function AdminProviderSyncPage() {
  const [keyInput, setKeyInput] = useState('');
  const [submittedKey, setSubmittedKey] = useState('');
  const [jobStatus, setJobStatus] =
    useState<(typeof IMPORT_JOB_STATUS_OPTIONS)[number]['value']>('running');

  const providerParams = useMemo<AdminProviderSyncListParams>(
    () => ({
      key: submittedKey || undefined,
    }),
    [submittedKey],
  );
  const importJobParams = useMemo<AdminProviderImportJobListParams>(
    () => ({
      status: jobStatus === 'all' ? undefined : jobStatus,
      pageSize: 50,
    }),
    [jobStatus],
  );

  const providersQuery = useQuery({
    queryKey: queryKeys.admin.providerSync(providerParams),
    queryFn: () => adminApi(apiClient).listProviderSync(providerParams),
    placeholderData: keepPreviousData,
  });

  const jobsQuery = useQuery({
    queryKey: queryKeys.admin.providerImportJobs(importJobParams),
    queryFn: () => adminApi(apiClient).listProviderImportJobs(importJobParams),
    placeholderData: keepPreviousData,
  });

  const providers = providersQuery.data?.items ?? [];
  const importJobs = jobsQuery.data?.items ?? [];

  const providerError = providersQuery.isError
    ? providersQuery.error instanceof ApiError
      ? providersQuery.error.message
      : 'provider sync 조회에 실패했습니다.'
    : null;
  const jobsError = jobsQuery.isError
    ? jobsQuery.error instanceof ApiError
      ? jobsQuery.error.message
      : 'import job 조회에 실패했습니다.'
    : null;

  const providerColumns: AdminTableColumn<AdminProviderDatasetSummary>[] = [
    {
      key: 'provider',
      header: 'provider',
      sortable: true,
      sortValue: (item) => `${item.provider}:${item.dataset_key}`,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.provider}</div>
          <div className="font-mono text-xs text-muted">{item.dataset_key}</div>
        </div>
      ),
    },
    {
      key: 'scope',
      header: 'scope',
      sortable: true,
      sortValue: (item) => item.sync_scope,
      cell: (item) => item.sync_scope,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => statusLabel(item.status),
    },
    {
      key: 'last_success',
      header: '최근 성공',
      sortable: true,
      sortValue: (item) => (item.last_success_at ? new Date(item.last_success_at).getTime() : 0),
      cell: (item) => formatDateTime(item.last_success_at),
    },
    {
      key: 'failures',
      header: '연속 실패',
      sortable: true,
      sortValue: (item) => item.consecutive_failures,
      cell: (item) => item.consecutive_failures.toLocaleString('ko-KR'),
      align: 'right',
    },
    {
      key: 'next_run',
      header: '다음 실행',
      sortable: true,
      sortValue: (item) => (item.next_run_after ? new Date(item.next_run_after).getTime() : 0),
      cell: (item) => formatDateTime(item.next_run_after),
    },
  ];

  const jobColumns: AdminTableColumn<AdminProviderImportJobRecord>[] = [
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
  ];

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedKey(keyInput.trim());
  };

  return (
    <AdminPage
      title="Provider sync"
      description="kor-travel-map provider/dataset 수집 상태와 import job 실행 이력"
      actions={
        <button
          type="button"
          onClick={() => {
            void providersQuery.refetch();
            void jobsQuery.refetch();
          }}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-provider-sync-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-provider-sync-key" className="text-xs text-muted">
            provider/dataset
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              id="admin-provider-sync-key"
              value={keyInput}
              onChange={(event) => setKeyInput(event.target.value)}
              className={`${inputClass} w-56 pl-7`}
              placeholder="kma, visitkorea..."
              data-testid="admin-provider-sync-key"
            />
          </div>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-provider-sync-submit"
          >
            조회
          </button>
        </form>
        <label htmlFor="admin-provider-sync-job-status" className="text-xs text-muted">
          job
        </label>
        <select
          id="admin-provider-sync-job-status"
          value={jobStatus}
          onChange={(event) => setJobStatus(event.target.value as typeof jobStatus)}
          className={inputClass}
          data-testid="admin-provider-sync-job-status"
        >
          {IMPORT_JOB_STATUS_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">{providers.length} datasets</span>
      </FilterBar>

      {providerError && <ErrorBox message={providerError} />}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Provider datasets
        </h2>
        <AdminTable
          columns={providerColumns}
          rows={providers}
          loading={providersQuery.isLoading}
          rowKey={(item) => `${item.provider}:${item.dataset_key}`}
          rowTestId={(item) => `admin-provider-row-${item.provider}-${item.dataset_key}`}
          empty="provider sync 상태가 없습니다."
        />
      </section>

      {jobsError && <ErrorBox message={jobsError} />}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Import jobs</h2>
        <AdminTable
          columns={jobColumns}
          rows={importJobs}
          loading={jobsQuery.isLoading}
          rowKey={(item) => item.job_id}
          rowTestId={(item) => `admin-provider-job-row-${item.job_id}`}
          empty="조회된 import job이 없습니다."
        />
      </section>
    </AdminPage>
  );
}
