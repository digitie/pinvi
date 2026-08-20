'use client';

import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type {
  AdminFeatureReferenceReconciliationDetail,
  AdminFeatureReferenceReconciliationSummary,
} from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'blocked', label: 'blocked' },
  { value: 'applied', label: 'applied' },
] as const;

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

function EvidenceDetail({
  detail,
  onClose,
}: {
  detail: AdminFeatureReferenceReconciliationDetail;
  onClose: () => void;
}) {
  return (
    <section
      className="space-y-3 rounded-sm border border-hairline bg-surface-soft p-4"
      data-testid="admin-frr-detail"
    >
      <header className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-ink">{detail.status}</h2>
          <p className="break-all text-xs text-muted">event: {detail.event_id}</p>
        </div>
        <button type="button" onClick={onClose} className="text-xs text-muted hover:text-ink">
          닫기
        </button>
      </header>

      {detail.receipt ? (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
          <dt className="text-muted">action</dt>
          <dd>{detail.receipt.action}</dd>
          <dt className="text-muted">이전 Feature</dt>
          <dd className="break-all">{detail.receipt.old_feature_id}</dd>
          <dt className="text-muted">대체 Feature</dt>
          <dd className="break-all">{detail.receipt.replacement_feature_id ?? '—'}</dd>
          <dt className="text-muted">영향 행</dt>
          <dd>{detail.receipt.impact_count}</dd>
          <dt className="text-muted">receipt SHA-256</dt>
          <dd className="break-all">{detail.receipt.receipt_sha256}</dd>
        </dl>
      ) : (
        <p className="text-xs text-warning-text">
          local mutation과 ACK를 중단한 blocked event입니다. 아래 관측 hash로 원인을 확인하세요.
        </p>
      )}

      <div>
        <h3 className="mb-1 text-xs font-semibold text-ink">관측</h3>
        <ul className="space-y-1 text-xs">
          {detail.attempts.map((attempt) => (
            <li key={attempt.attempt_sequence} className="rounded-sm border border-hairline p-2">
              #{attempt.attempt_sequence} · {attempt.status} · {formatDateTime(attempt.observed_at)}
              {attempt.block_fingerprint_sha256 && (
                <p className="break-all text-muted">block: {attempt.block_fingerprint_sha256}</p>
              )}
              <p className="break-all text-muted">observation: {attempt.observation_root_sha256}</p>
            </li>
          ))}
        </ul>
      </div>

      {detail.impacts.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-ink">영향 행</h3>
          <ul className="space-y-1 text-xs">
            {detail.impacts.map((impact) => (
              <li
                key={`${impact.target_relation}:${impact.target_id}`}
                className="rounded-sm border border-hairline p-2"
              >
                {impact.target_relation} · {impact.outcome} · {impact.target_id}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default function AdminFeatureReferenceReconciliationsPage() {
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]['value']>('all');
  const [page, setPage] = useState(1);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const listQuery = useQuery({
    queryKey: queryKeys.admin.featureReferenceReconciliations({ status: statusFilter, page }),
    queryFn: () =>
      adminApi(apiClient).listFeatureReferenceReconciliations({
        status: statusFilter,
        page,
        limit: 50,
      }),
    placeholderData: keepPreviousData,
  });
  const detailQuery = useQuery({
    queryKey: queryKeys.admin.featureReferenceReconciliation(selectedEventId ?? ''),
    queryFn: () => adminApi(apiClient).getFeatureReferenceReconciliation(selectedEventId ?? ''),
    enabled: selectedEventId !== null,
  });

  const data = listQuery.data;
  const error = listQuery.isError
    ? listQuery.error instanceof ApiError
      ? listQuery.error.message
      : '증거 목록을 불러오지 못했습니다.'
    : null;
  const columns: AdminTableColumn<AdminFeatureReferenceReconciliationSummary>[] = [
    {
      key: 'event_sequence',
      header: '순번',
      sortable: true,
      sortValue: (row) => row.event_sequence,
      cell: (row) => row.event_sequence,
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (row) => row.status,
      cell: (row) => row.status,
    },
    {
      key: 'event_id',
      header: 'event',
      cell: (row) => <span className="font-mono text-xs">{row.event_id.slice(0, 12)}…</span>,
    },
    {
      key: 'attempt',
      header: '최근 관측',
      cell: (row) => `#${row.latest_attempt.attempt_sequence}`,
    },
    {
      key: 'observed_at',
      header: '시각',
      sortable: true,
      sortValue: (row) => new Date(row.observed_at).getTime(),
      cell: (row) => formatDateTime(row.observed_at),
    },
    {
      key: 'detail',
      header: '',
      cell: (row) => (
        <button
          type="button"
          className="rounded-sm border border-hairline px-2 py-1 text-xs"
          data-testid={`admin-frr-detail-${row.event_id}`}
          onClick={() => setSelectedEventId(row.event_id)}
        >
          증거
        </button>
      ),
    },
  ];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  return (
    <AdminPage
      title="Feature 참조 조정 증거"
      description="Map M05 event의 PinVi append-only receipt, blocked 관측 및 영향 행을 읽기 전용으로 확인합니다."
    >
      <FilterBar>
        <label htmlFor="admin-frr-status" className="text-xs text-muted">
          상태
        </label>
        <select
          id="admin-frr-status"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value as (typeof STATUS_FILTERS)[number]['value']);
            setPage(1);
            setSelectedEventId(null);
          }}
          className="rounded-sm border border-hairline bg-canvas px-2 py-1 text-sm"
        >
          {STATUS_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>
              {filter.label}
            </option>
          ))}
        </select>
      </FilterBar>

      {error && (
        <p role="alert" className="text-sm text-error-text">
          {error}
        </p>
      )}
      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        rowKey={(row) => row.event_id}
        loading={listQuery.isLoading}
        empty="아직 Map Feature 참조 조정 증거가 없습니다."
      />
      <div className="flex items-center gap-2 text-sm">
        <button
          type="button"
          disabled={page <= 1}
          className="rounded-sm border border-hairline px-2 py-1 disabled:opacity-50"
          onClick={() => setPage((current) => current - 1)}
        >
          이전
        </button>
        <span>
          {page} / {totalPages} · {total}건
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          className="rounded-sm border border-hairline px-2 py-1 disabled:opacity-50"
          onClick={() => setPage((current) => current + 1)}
        >
          다음
        </button>
      </div>

      {detailQuery.isError && (
        <p role="alert" className="text-sm text-error-text">
          증거 상세를 불러오지 못했습니다.
        </p>
      )}
      {detailQuery.data && (
        <EvidenceDetail detail={detailQuery.data} onClose={() => setSelectedEventId(null)} />
      )}
    </AdminPage>
  );
}
