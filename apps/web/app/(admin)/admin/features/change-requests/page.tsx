'use client';

import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminFeatureChangeRequestListParams,
} from '@pinvi/api-client';
import type {
  AdminFeatureChangeRequestPagedResponse,
  AdminFeatureChangeRequestRecord,
} from '@pinvi/schemas';
import { Check, RefreshCw, Search, X } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_OPTIONS = [
  { value: 'pending', label: '대기' },
  { value: 'applied', label: '반영' },
  { value: 'rejected', label: '거절' },
  { value: 'all', label: '전체' },
] as const;

const ACTION_OPTIONS = [
  { value: 'all', label: '액션 전체' },
  { value: 'add', label: '추가' },
  { value: 'update', label: '수정' },
  { value: 'delete', label: '삭제' },
] as const;

const STATUS_LABEL: Record<string, string> = {
  pending: '대기',
  applied: '반영',
  rejected: '거절',
  failed: '실패',
};

const ACTION_LABEL: Record<string, string> = {
  add: '추가',
  update: '수정',
  delete: '삭제',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-sm bg-surface-soft p-3 text-xs leading-relaxed text-body">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function applyOptimisticStatus(
  old: AdminFeatureChangeRequestPagedResponse | undefined,
  requestId: string,
  status: 'applied' | 'rejected',
  reason: string,
) {
  if (!old) return old;
  const now = new Date().toISOString();
  return {
    ...old,
    items: old.items.map((item) =>
      item.request_id === requestId
        ? {
            ...item,
            status,
            reviewed_at: now,
            reason: item.reason ?? reason,
            applied_at: status === 'applied' ? now : item.applied_at,
          }
        : item,
    ),
  };
}

function mergeRecord(
  old: AdminFeatureChangeRequestPagedResponse | undefined,
  record: AdminFeatureChangeRequestRecord,
) {
  if (!old) return old;
  return {
    ...old,
    items: old.items.map((item) => (item.request_id === record.request_id ? record : item)),
  };
}

function DetailPanel({
  record,
  onClose,
}: {
  record: AdminFeatureChangeRequestRecord;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accessReason, setAccessReason] = useState('');
  const [mapReason, setMapReason] = useState('');
  const [mutationError, setMutationError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: ({
      action,
      requestId,
      body,
    }: {
      action: 'approve' | 'reject';
      requestId: string;
      body: { access_reason: string; kor_travel_map_reason?: string };
    }) =>
      action === 'approve'
        ? adminApi(apiClient).approveFeatureChangeRequest(requestId, body)
        : adminApi(apiClient).rejectFeatureChangeRequest(requestId, body),
    onMutate: async (variables) => {
      setMutationError(null);
      await queryClient.cancelQueries({
        queryKey: queryKeys.admin.featureChangeRequestsAll(),
      });
      const previous =
        queryClient.getQueriesData<AdminFeatureChangeRequestPagedResponse>({
          queryKey: queryKeys.admin.featureChangeRequestsAll(),
        });
      queryClient.setQueriesData<AdminFeatureChangeRequestPagedResponse>(
        { queryKey: queryKeys.admin.featureChangeRequestsAll() },
        (old) =>
          applyOptimisticStatus(
            old,
            variables.requestId,
            variables.action === 'approve' ? 'applied' : 'rejected',
            variables.body.kor_travel_map_reason ?? variables.body.access_reason,
          ),
      );
      return { previous };
    },
    onError: (error, _variables, context) => {
      for (const [key, value] of context?.previous ?? []) {
        queryClient.setQueryData(key, value);
      }
      setMutationError(
        error instanceof ApiError ? error.message : '변경 요청 처리에 실패했습니다.',
      );
    },
    onSuccess: (updated) => {
      queryClient.setQueriesData<AdminFeatureChangeRequestPagedResponse>(
        { queryKey: queryKeys.admin.featureChangeRequestsAll() },
        (old) => mergeRecord(old, updated),
      );
      void queryClient.invalidateQueries({
        queryKey: queryKeys.admin.featureChangeRequestsAll(),
      });
      void queryClient.invalidateQueries({ queryKey: ['admin', 'features'] });
      setAccessReason('');
      setMapReason('');
    },
  });

  const busy = mutation.isPending;
  const pending = record.status === 'pending';

  const submit = (action: 'approve' | 'reject') => {
    if (!accessReason.trim()) {
      setMutationError('운영 사유를 입력하세요.');
      return;
    }
    mutation.mutate({
      action,
      requestId: record.request_id,
      body: {
        access_reason: accessReason.trim(),
        kor_travel_map_reason: mapReason.trim() || undefined,
      },
    });
  };

  return (
    <section
      className="space-y-4 rounded-sm border border-hairline bg-white p-4"
      data-testid="admin-fcr-detail"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">
            {ACTION_LABEL[record.action] ?? record.action} /{' '}
            {STATUS_LABEL[record.status] ?? record.status}
          </h2>
          <p className="break-all font-mono text-xs text-muted">{record.request_id}</p>
        </div>
        <button type="button" onClick={onClose} className="text-xs text-muted hover:text-ink">
          닫기
        </button>
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-muted">feature</dt>
        <dd className="break-all font-mono">{record.feature_id}</dd>
        <dt className="text-muted">review mode</dt>
        <dd>{record.review_mode}</dd>
        <dt className="text-muted">requested by</dt>
        <dd>{record.requested_by ?? '—'}</dd>
        <dt className="text-muted">reviewed by</dt>
        <dd>{record.reviewed_by ?? '—'}</dd>
        <dt className="text-muted">created</dt>
        <dd>{formatDateTime(record.created_at)}</dd>
        <dt className="text-muted">reviewed</dt>
        <dd>{formatDateTime(record.reviewed_at)}</dd>
        <dt className="text-muted">applied</dt>
        <dd>{formatDateTime(record.applied_at)}</dd>
        <dt className="text-muted">reason</dt>
        <dd>{record.reason ?? '—'}</dd>
      </dl>

      <details open>
        <summary className="cursor-pointer text-sm font-medium">payload</summary>
        <div className="mt-2">
          <JsonBlock value={record.payload} />
        </div>
      </details>

      {mutation.isSuccess && (
        <p
          className="rounded-sm bg-surface-soft p-3 text-sm text-body"
          data-testid="admin-fcr-notice"
        >
          변경 요청 처리 결과를 갱신했습니다.
        </p>
      )}

      {pending ? (
        <form
          className="space-y-2 border-t border-hairline pt-3"
          onSubmit={(event: FormEvent<HTMLFormElement>) => event.preventDefault()}
        >
          <label className="block text-xs text-muted">
            운영 사유 (Pinvi audit)
            <textarea
              value={accessReason}
              onChange={(event) => setAccessReason(event.target.value)}
              className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
              rows={2}
              data-testid="admin-fcr-reason"
            />
          </label>
          <label className="block text-xs text-muted">
            kor_travel_map 전달 사유
            <textarea
              value={mapReason}
              onChange={(event) => setMapReason(event.target.value)}
              className="mt-1 w-full rounded-sm border border-hairline px-2 py-1 text-sm"
              rows={2}
              data-testid="admin-fcr-map-reason"
            />
          </label>
          {mutationError && (
            <p
              role="alert"
              className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
              data-testid="admin-fcr-mutation-error"
            >
              {mutationError}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => submit('approve')}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
              data-testid="admin-fcr-approve"
            >
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
              승인
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => submit('reject')}
              className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
              data-testid="admin-fcr-reject"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              거절
            </button>
          </div>
        </form>
      ) : (
        <p className="border-t border-hairline pt-3 text-sm text-muted">
          이 변경 요청은 이미 처리되었습니다.
        </p>
      )}
    </section>
  );
}

export default function AdminFeatureChangeRequestsPage() {
  const [queryInput, setQueryInput] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]['value']>(
    'pending',
  );
  const [actionFilter, setActionFilter] = useState<(typeof ACTION_OPTIONS)[number]['value']>(
    'all',
  );
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);

  useEffect(() => {
    const initialQ = new URLSearchParams(window.location.search).get('q')?.trim() ?? '';
    if (initialQ) {
      setQueryInput(initialQ);
      setSubmittedQ(initialQ);
    }
  }, []);

  const params = useMemo<AdminFeatureChangeRequestListParams>(
    () => ({
      q: submittedQ || undefined,
      status: statusFilter === 'all' ? undefined : [statusFilter],
      action: actionFilter === 'all' ? undefined : [actionFilter],
      pageSize: 100,
    }),
    [actionFilter, statusFilter, submittedQ],
  );

  const changeRequestsQuery = useQuery({
    queryKey: queryKeys.admin.featureChangeRequests(params),
    queryFn: () => adminApi(apiClient).listFeatureChangeRequests(params),
    placeholderData: keepPreviousData,
  });

  const data = changeRequestsQuery.data ?? null;
  const selected =
    data?.items.find((item) => item.request_id === selectedRequestId) ??
    (selectedRequestId ? null : null);
  const error = changeRequestsQuery.isError
    ? changeRequestsQuery.error instanceof ApiError
      ? changeRequestsQuery.error.message
      : '변경 요청 조회에 실패했습니다.'
    : null;

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQ(queryInput.trim());
    setSelectedRequestId(null);
  };

  const columns: AdminTableColumn<AdminFeatureChangeRequestRecord>[] = [
    {
      key: 'request',
      header: 'request',
      sortable: true,
      sortValue: (item) => item.request_id,
      cell: (item) => (
        <div>
          <div className="break-all font-mono text-xs">{item.request_id}</div>
          <div className="break-all font-mono text-xs text-muted">{item.feature_id}</div>
        </div>
      ),
    },
    {
      key: 'action',
      header: '액션',
      sortable: true,
      sortValue: (item) => item.action,
      cell: (item) => ACTION_LABEL[item.action] ?? item.action,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => (
        <span data-testid={`admin-fcr-status-${item.request_id}`}>
          {STATUS_LABEL[item.status] ?? item.status}
        </span>
      ),
    },
    {
      key: 'requested_by',
      header: '요청자',
      sortable: true,
      sortValue: (item) => item.requested_by ?? '',
      cell: (item) => item.requested_by ?? '—',
    },
    {
      key: 'created_at',
      header: '생성',
      sortable: true,
      sortValue: (item) => new Date(item.created_at).getTime(),
      cell: (item) => formatDateTime(item.created_at),
    },
    {
      key: 'reviewed_at',
      header: '검수',
      sortable: true,
      sortValue: (item) => (item.reviewed_at ? new Date(item.reviewed_at).getTime() : 0),
      cell: (item) => formatDateTime(item.reviewed_at),
    },
    {
      key: 'action_button',
      header: '',
      cell: (item) => (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            setSelectedRequestId(item.request_id);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-xs"
          data-testid={`admin-fcr-select-${item.request_id}`}
        >
          상세
        </button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Feature 변경 요청"
      description="kor-travel-map admin change request 큐 검수와 적용 상태 추적"
    >
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-fcr-search" className="text-xs text-muted">
            검색
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              id="admin-fcr-search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className={`${inputClass} w-56 pl-7`}
              placeholder="request, feature, reason"
              data-testid="admin-fcr-search"
            />
          </div>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-fcr-search-submit"
          >
            조회
          </button>
        </form>

        <select
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value as typeof statusFilter);
            setSelectedRequestId(null);
          }}
          className={inputClass}
          data-testid="admin-fcr-status-filter"
        >
          {STATUS_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <select
          value={actionFilter}
          onChange={(event) => {
            setActionFilter(event.target.value as typeof actionFilter);
            setSelectedRequestId(null);
          }}
          className={inputClass}
          data-testid="admin-fcr-action-filter"
        >
          {ACTION_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={changeRequestsQuery.isFetching}
          onClick={() => void changeRequestsQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
          data-testid="admin-fcr-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
        <span className="ml-auto text-xs text-muted">
          {data?.items.length ?? 0}행
          {data?.review_mode ? ` / ${data.review_mode}` : ''}
        </span>
      </FilterBar>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-fcr-error"
        >
          {error}
        </p>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_30rem]">
        <AdminTable
          columns={columns}
          rows={data?.items ?? []}
          loading={changeRequestsQuery.isLoading}
          rowKey={(item) => item.request_id}
          rowTestId={(item) => `admin-fcr-row-${item.request_id}`}
          onRowClick={(item) => setSelectedRequestId(item.request_id)}
          empty="변경 요청이 없습니다."
        />

        {selected ? (
          <DetailPanel record={selected} onClose={() => setSelectedRequestId(null)} />
        ) : (
          <section
            className="rounded-sm border border-hairline bg-white p-4 text-sm text-muted"
            data-testid="admin-fcr-detail-empty"
          >
            목록에서 변경 요청을 선택하면 payload와 검수 액션이 표시됩니다.
          </section>
        )}
      </section>
    </AdminPage>
  );
}
