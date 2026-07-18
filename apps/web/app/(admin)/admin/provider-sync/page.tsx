'use client';

import { useMemo, useState, type FormEvent } from 'react';
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type Query,
} from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  authApi,
  queryKeys,
  type AdminProviderImportJobListParams,
  type AdminProviderSyncListParams,
} from '@pinvi/api-client';
import type { AdminProviderDatasetSummary, AdminProviderImportJobRecord } from '@pinvi/schemas';
import { Ban, RefreshCw, Search, X } from 'lucide-react';
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
  in_progress: '취소 진행 중',
  retryable: '취소 재시도 가능',
  completed: '취소 완료',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';
const CANCEL_REASON_MAX_LENGTH = 500;
const DETERMINISTIC_CANCEL_REJECTION_STATUSES = new Set([400, 401, 403, 422, 429]);

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function statusLabel(value: string | null | undefined) {
  return value ? (STATUS_LABEL[value] ?? value) : '—';
}

function progressLabel(value: number | null | undefined) {
  if (typeof value !== 'number') return '—';
  return `${value}%`;
}

function cancelAction(
  item: AdminProviderImportJobRecord,
  reconciling: boolean,
  canCancel: boolean,
) {
  if (!canCancel) return null;
  if (reconciling) {
    return { enabled: false, label: '상태 확인 중' };
  }
  if (item.cancellation?.status === 'in_progress') {
    return { enabled: false, label: '취소 진행 중' };
  }
  if (item.cancellation?.status === 'retryable') {
    return { enabled: true, label: '취소 재시도' };
  }
  if (item.cancellation?.status === 'failed') {
    return { enabled: false, label: '취소 실패' };
  }
  if (item.cancellation?.status === 'completed') {
    return { enabled: false, label: '취소 완료' };
  }
  if (item.status === 'queued' || item.status === 'running') {
    return { enabled: true, label: '취소' };
  }
  return null;
}

function reconciliationPending(item: AdminProviderImportJobRecord | undefined) {
  if (!item) return true;
  if (item.cancellation) return item.cancellation.status === 'in_progress';
  return item.status === 'queued' || item.status === 'running';
}

function cancellationWarning(error: ApiError) {
  const details = error.details ?? {};
  const detailStatus = typeof details.status === 'string' ? details.status : null;
  const unresolved =
    typeof details.unresolved_member_count === 'number'
      ? details.unresolved_member_count
      : null;
  const warnings = Array.isArray(details.warnings)
    ? details.warnings.filter((item): item is string => typeof item === 'string')
    : [];
  const retryAfter =
    error.retryAfterSeconds === undefined ? null : `${error.retryAfterSeconds}초 후 조회 가능`;
  return [
    `HTTP ${error.status}`,
    error.code,
    error.message,
    detailStatus ? `취소 상태=${detailStatus}` : null,
    unresolved === null ? null : `미해결=${unresolved}`,
    retryAfter,
    ...warnings,
    'canonical 상세 상태를 확인하기 전에는 취소를 재시도할 수 없습니다.',
  ]
    .filter(Boolean)
    .join(' · ');
}

function isDeterministicCancelRejection(error: unknown): error is ApiError {
  if (!(error instanceof ApiError)) return false;
  return (
    DETERMINISTIC_CANCEL_REJECTION_STATUSES.has(error.status) ||
    (error.status === 404 && error.code === 'PIPELINE_EXECUTION_NOT_FOUND')
  );
}

function cancellationRejection(error: ApiError) {
  const retryAfter =
    error.retryAfterSeconds === undefined ? null : `${error.retryAfterSeconds}초 후 재시도 가능`;
  return [`HTTP ${error.status}`, error.code, error.message, retryAfter]
    .filter(Boolean)
    .join(' · ');
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
  const queryClient = useQueryClient();
  const [keyInput, setKeyInput] = useState('');
  const [submittedKey, setSubmittedKey] = useState('');
  const [jobStatus, setJobStatus] =
    useState<(typeof IMPORT_JOB_STATUS_OPTIONS)[number]['value']>('running');
  const [jobCursor, setJobCursor] = useState<string | null>(null);
  const [jobCursorHistory, setJobCursorHistory] = useState<Array<string | null>>([]);
  const [cancelJobId, setCancelJobId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelMapReason, setCancelMapReason] = useState('');
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [reconciliationMessages, setReconciliationMessages] = useState<
    Record<string, { warning?: string; notice?: string }>
  >({});
  const [reconciliationJobIds, setReconciliationJobIds] = useState<string[]>([]);

  const meQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: () => authApi(apiClient).me(),
    staleTime: 60_000,
  });
  const canCancel = meQuery.data?.roles.includes('admin') ?? false;

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
      cursor: jobCursor ?? undefined,
    }),
    [jobCursor, jobStatus],
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

  const reconciliationQueries = useQueries({
    queries: reconciliationJobIds.map((jobId) => ({
      queryKey: queryKeys.admin.providerImportJob(jobId),
      queryFn: () => adminApi(apiClient).getProviderImportJob(jobId),
      refetchInterval: (query: Query<AdminProviderImportJobRecord>) =>
        reconciliationPending(query.state.data) ? 2_000 : false,
    })),
  });
  const reconciliationByJobId = new Map(
    reconciliationJobIds.map((jobId, index) => [jobId, reconciliationQueries[index]] as const),
  );

  const beginReconciliation = (jobId: string, refreshLists: boolean) => {
    void queryClient.resetQueries({
      queryKey: queryKeys.admin.providerImportJob(jobId),
      exact: true,
    });
    setReconciliationJobIds((current) =>
      current.includes(jobId) ? current : [...current, jobId],
    );
    if (refreshLists) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.providerImportJobsAll() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.providerSyncAll() });
      void jobsQuery.refetch();
      void providersQuery.refetch();
    }
  };

  const stopReconciliation = (jobId: string) => {
    setReconciliationJobIds((current) => current.filter((item) => item !== jobId));
    void queryClient.cancelQueries({
      queryKey: queryKeys.admin.providerImportJob(jobId),
      exact: true,
    });
  };

  const providers = providersQuery.data?.items ?? [];
  const importJobs = (jobsQuery.data?.items ?? []).map(
    (item) => reconciliationByJobId.get(item.job_id)?.data ?? item,
  );
  const jobPaginationLocked = jobsQuery.isFetching || jobsQuery.isPlaceholderData;
  const reconciliationLockedJobIds = new Set(
    reconciliationJobIds.filter((jobId) => {
      const query = reconciliationByJobId.get(jobId);
      return query?.isError || reconciliationPending(query?.data);
    }),
  );
  const cancelJob = importJobs.find((item) => item.job_id === cancelJobId) ?? null;

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

  const cancelMutation = useMutation({
    mutationFn: ({ item }: { item: AdminProviderImportJobRecord }) =>
      adminApi(apiClient).cancelProviderImportJob(item.job_id, {
        access_reason: cancelReason.trim(),
        kor_travel_map_reason: cancelMapReason.trim() || undefined,
      }),
    onMutate: ({ item }) => {
      setMutationError(null);
      setReconciliationMessages((current) => {
        const next = { ...current };
        delete next[item.job_id];
        return next;
      });
    },
    onError: (error, variables) => {
      if (isDeterministicCancelRejection(error)) {
        stopReconciliation(variables.item.job_id);
        setMutationError(cancellationRejection(error));
        return;
      }
      setReconciliationMessages((current) => ({
        ...current,
        [variables.item.job_id]: {
          warning:
            error instanceof ApiError
              ? cancellationWarning(error)
              : '취소 요청 응답을 확인하지 못했습니다. canonical 상세 상태를 확인하기 전에는 ' +
                '취소를 재시도할 수 없습니다.',
        },
      }));
      beginReconciliation(variables.item.job_id, true);
      setCancelJobId(null);
    },
    onSuccess: (result) => {
      const warnings = result.warnings.length ? result.warnings.join(' / ') : '없음';
      setReconciliationMessages((current) => ({
        ...current,
        [result.requested_job_id]: {
          notice:
            `${result.requested_job_id} 취소 결과 status=${result.status}` +
            `(${statusLabel(result.status)}) · canonical root ` +
            `${result.root_kind}:${result.root_id} · warnings=${warnings}`,
        },
      }));
      setCancelJobId(null);
      beginReconciliation(result.requested_job_id, true);
      setCancelReason('');
      setCancelMapReason('');
    },
  });

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
      key: 'eligible_after',
      header: '재호출 가능',
      sortable: true,
      sortValue: (item) => (item.eligible_after ? new Date(item.eligible_after).getTime() : 0),
      cell: (item) => formatDateTime(item.eligible_after),
    },
    {
      key: 'schedule_next',
      header: '다음 예약',
      sortable: true,
      sortValue: (item) =>
        item.schedule_next_scheduled_at
          ? new Date(item.schedule_next_scheduled_at).getTime()
          : 0,
      cell: (item) => formatDateTime(item.schedule_next_scheduled_at),
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
          <div className="text-xs text-muted">
            대표 {item.projected_job_kind} · {item.projected_job_id}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => (
        <div>
          <div>{statusLabel(item.status)}</div>
          <div className="text-xs text-muted">
            대표 job {statusLabel(item.projected_job_status)}
          </div>
        </div>
      ),
    },
    {
      key: 'progress',
      header: '진행',
      sortable: true,
      sortValue: (item) => item.progress ?? 0,
      cell: (item) => (
        <div>
          <div>{progressLabel(item.progress)}</div>
          <div className="text-xs text-muted">
            대표 job {progressLabel(item.projected_job_progress)}
          </div>
        </div>
      ),
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
      key: 'actions',
      header: '작업',
      cell: (item) => {
        const reconciling =
          jobPaginationLocked || reconciliationLockedJobIds.has(item.job_id);
        const action = cancelAction(item, reconciling, canCancel);
        return action ? (
          <button
            type="button"
            disabled={!action.enabled}
            onClick={() => {
              if (!action.enabled) return;
              setCancelJobId(item.job_id);
              setCancelReason('');
              setCancelMapReason('');
              setMutationError(null);
              setReconciliationMessages((current) => {
                const next = { ...current };
                delete next[item.job_id];
                return next;
              });
            }}
            className="inline-flex items-center gap-1 rounded-sm border border-hairline px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
            data-testid={`admin-provider-job-cancel-${item.job_id}`}
          >
            <Ban className="h-3.5 w-3.5" aria-hidden="true" />
            {action.label}
          </button>
        ) : (
          '—'
        );
      },
    },
  ];

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedKey(keyInput.trim());
  };

  const submitCancel = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!cancelJob || jobPaginationLocked) return;
    const reason = cancelReason.trim();
    const mapReason = cancelMapReason.trim();
    if (!reason) {
      setMutationError('운영 사유를 입력하세요.');
      return;
    }
    if (reason.length > CANCEL_REASON_MAX_LENGTH) {
      setMutationError(`운영 사유는 ${CANCEL_REASON_MAX_LENGTH}자 이하로 입력하세요.`);
      return;
    }
    if (mapReason.length > CANCEL_REASON_MAX_LENGTH) {
      setMutationError(`kor_travel_map 전달 사유는 ${CANCEL_REASON_MAX_LENGTH}자 이하로 입력하세요.`);
      return;
    }
    cancelMutation.mutate({ item: cancelJob });
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
          onChange={(event) => {
            setJobStatus(event.target.value as typeof jobStatus);
            setJobCursor(null);
            setJobCursorHistory([]);
            setCancelJobId(null);
          }}
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
      {providersQuery.data && providersQuery.data.schedule_source_status !== 'ok' && (
        <p
          role="status"
          className="rounded-sm border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
          data-testid="admin-provider-schedule-source-warning"
        >
          Dagster schedule 출처가 {providersQuery.data.schedule_source_status} 상태입니다.
          {providersQuery.data.schedule_source_errors.length
            ? ` ${providersQuery.data.schedule_source_errors.join(' / ')}`
            : ' 다음 예약 시각이 불완전할 수 있습니다.'}
        </p>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Provider datasets
        </h2>
        <AdminTable
          columns={providerColumns}
          rows={providers}
          loading={providersQuery.isLoading}
          rowKey={(item) => `${item.provider}:${item.dataset_key}:${item.sync_scope}`}
          rowTestId={(item) =>
            `admin-provider-row-${item.provider}-${item.dataset_key}-${item.sync_scope}`
          }
          empty="provider sync 상태가 없습니다."
        />
      </section>

      {jobsError && <ErrorBox message={jobsError} />}
      {mutationError && <ErrorBox message={mutationError} />}
      {Object.entries(reconciliationMessages).map(([messageJobId, message]) => {
        const reconciliation = reconciliationByJobId.get(messageJobId);
        return (
          <div key={messageJobId} data-reconciliation-job-id={messageJobId}>
            {message.warning && (
              <p
                role="alert"
                className="rounded-sm border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
                data-testid="admin-provider-cancel-warning"
              >
                {message.warning}
                {reconciliation?.data?.cancellation?.status === 'retryable' &&
                  ' canonical 상세 재조회에서 retryable 상태가 확인되어 재시도할 수 있습니다.'}
              </p>
            )}
            {message.notice && (
              <p
                className="rounded-sm bg-surface-soft p-3 text-sm text-body"
                data-testid="admin-provider-sync-mutation-notice"
              >
                {message.notice}
              </p>
            )}
          </div>
        );
      })}
      {reconciliationJobIds
        .filter(
          (reconciliationJobId) =>
            reconciliationByJobId.get(reconciliationJobId)?.isError,
        )
        .map((reconciliationJobId) => (
          <div
            key={reconciliationJobId}
            data-reconciliation-job-id={reconciliationJobId}
          >
            <ErrorBox
              message="취소 결과 상세 조회에 실패했습니다. 안전을 위해 재시도는 계속 잠겨 있습니다."
            />
          </div>
        ))}

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
        <div className="flex items-center justify-end gap-2 text-xs text-muted">
          <button
            type="button"
            disabled={jobPaginationLocked || jobCursorHistory.length === 0}
            onClick={() => {
              if (jobPaginationLocked || jobCursorHistory.length === 0) return;
              const previousCursor = jobCursorHistory[jobCursorHistory.length - 1] ?? null;
              setJobCursorHistory(jobCursorHistory.slice(0, -1));
              setJobCursor(previousCursor);
              setCancelJobId(null);
            }}
            className="rounded-sm border border-hairline px-2 py-1 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="admin-provider-jobs-prev"
          >
            이전
          </button>
          <span data-testid="admin-provider-jobs-page">
            {jobCursorHistory.length + 1} 페이지
          </span>
          <button
            type="button"
            disabled={jobPaginationLocked || !jobsQuery.data?.next_cursor}
            onClick={() => {
              const nextCursor = jobsQuery.data?.next_cursor;
              if (jobPaginationLocked || !nextCursor || nextCursor === jobCursor) return;
              setJobCursorHistory([...jobCursorHistory, jobCursor]);
              setJobCursor(nextCursor);
              setCancelJobId(null);
            }}
            className="rounded-sm border border-hairline px-2 py-1 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="admin-provider-jobs-next"
          >
            다음
          </button>
        </div>
      </section>

      {cancelJob && (
        <section
          className="space-y-3 rounded-sm border border-hairline bg-white p-4 text-sm"
          data-testid="admin-provider-job-cancel-panel"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink">Import job 취소</h2>
              <p className="break-all font-mono text-xs text-muted">{cancelJob.job_id}</p>
            </div>
            <button
              type="button"
              onClick={() => setCancelJobId(null)}
              className="rounded-sm border border-hairline p-1 text-muted hover:text-ink"
              aria-label="닫기"
              data-testid="admin-provider-job-cancel-close"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          <form className="space-y-3" onSubmit={submitCancel}>
            <label className="block text-xs text-muted">
              운영 사유 (Pinvi audit)
              <textarea
                value={cancelReason}
                onChange={(event) => setCancelReason(event.target.value)}
                className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                rows={2}
                maxLength={CANCEL_REASON_MAX_LENGTH}
                data-testid="admin-provider-job-cancel-reason"
              />
              <span
                className="mt-1 block text-right text-[11px]"
                data-testid="admin-provider-job-cancel-reason-count"
              >
                {cancelReason.length}/{CANCEL_REASON_MAX_LENGTH}
              </span>
            </label>
            <label className="block text-xs text-muted">
              kor_travel_map 전달 사유
              <textarea
                value={cancelMapReason}
                onChange={(event) => setCancelMapReason(event.target.value)}
                className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
                rows={2}
                maxLength={CANCEL_REASON_MAX_LENGTH}
                data-testid="admin-provider-job-cancel-map-reason"
              />
              <span
                className="mt-1 block text-right text-[11px]"
                data-testid="admin-provider-job-cancel-map-reason-count"
              >
                {cancelMapReason.length}/{CANCEL_REASON_MAX_LENGTH}
              </span>
            </label>
            <div className="flex items-center justify-end gap-2 border-t border-hairline pt-3">
              <button
                type="button"
                onClick={() => setCancelJobId(null)}
                className="rounded-sm border border-hairline px-3 py-1 text-sm"
                data-testid="admin-provider-job-cancel-abort"
              >
                닫기
              </button>
              <button
                type="submit"
                disabled={cancelMutation.isPending || jobPaginationLocked}
                className="inline-flex items-center gap-1 rounded-sm border border-ink bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
                data-testid="admin-provider-job-cancel-submit"
              >
                <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                취소 요청
              </button>
            </div>
          </form>
        </section>
      )}
    </AdminPage>
  );
}
