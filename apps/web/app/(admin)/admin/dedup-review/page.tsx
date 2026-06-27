'use client';

import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminDedupReviewListParams,
} from '@pinvi/api-client';
import type { AdminDedupReviewRecord } from '@pinvi/schemas';
import { RefreshCw, Search } from 'lucide-react';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_OPTIONS = [
  { value: 'pending', label: '대기' },
  { value: 'accepted', label: '수락' },
  { value: 'rejected', label: '거절' },
  { value: 'merged', label: '병합' },
  { value: 'ignored', label: '무시' },
  { value: 'all', label: '전체' },
] as const;

const STATUS_LABEL: Record<string, string> = {
  pending: '대기',
  accepted: '수락',
  rejected: '거절',
  merged: '병합',
  ignored: '무시',
};

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function score(value: number) {
  return Math.round(value).toLocaleString('ko-KR');
}

function featureLabel(item: AdminDedupReviewRecord['feature_a']) {
  return `${item.name} (${item.kind}/${item.category})`;
}

export default function AdminDedupReviewPage() {
  const [queryInput, setQueryInput] = useState('');
  const [submittedQ, setSubmittedQ] = useState('');
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_OPTIONS)[number]['value']>(
    'pending',
  );
  const [minScore, setMinScore] = useState('70');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const params = useMemo<AdminDedupReviewListParams>(
    () => ({
      q: submittedQ || undefined,
      status: statusFilter === 'all' ? undefined : [statusFilter],
      minScore: minScore.trim() ? Number(minScore) : undefined,
      pageSize: 50,
    }),
    [minScore, statusFilter, submittedQ],
  );

  const reviewsQuery = useQuery({
    queryKey: queryKeys.admin.dedupReviews(params),
    queryFn: () => adminApi(apiClient).listDedupReviews(params),
    placeholderData: keepPreviousData,
  });

  const data = reviewsQuery.data ?? null;
  const selected = data?.items.find((item) => item.review_id === selectedId) ?? null;
  const error = reviewsQuery.isError
    ? reviewsQuery.error instanceof ApiError
      ? reviewsQuery.error.message
      : 'dedup review 조회에 실패했습니다.'
    : null;

  const columns: AdminTableColumn<AdminDedupReviewRecord>[] = [
    {
      key: 'review',
      header: 'review',
      sortable: true,
      sortValue: (item) => item.review_id,
      cell: (item) => (
        <div>
          <div className="font-mono text-xs">{item.review_id}</div>
          <div className="text-xs text-muted">{formatDateTime(item.created_at)}</div>
        </div>
      ),
    },
    {
      key: 'score',
      header: 'score',
      sortable: true,
      sortValue: (item) => item.total_score,
      cell: (item) => score(item.total_score),
      align: 'right',
    },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (item) => item.status,
      cell: (item) => STATUS_LABEL[item.status] ?? item.status,
    },
    {
      key: 'feature_a',
      header: 'feature A',
      sortable: true,
      sortValue: (item) => item.feature_a.name,
      cell: (item) => (
        <div>
          <div>{item.feature_a.name}</div>
          <div className="font-mono text-xs text-muted">{item.feature_a.feature_id}</div>
        </div>
      ),
    },
    {
      key: 'feature_b',
      header: 'feature B',
      sortable: true,
      sortValue: (item) => item.feature_b.name,
      cell: (item) => (
        <div>
          <div>{item.feature_b.name}</div>
          <div className="font-mono text-xs text-muted">{item.feature_b.feature_id}</div>
        </div>
      ),
    },
    {
      key: 'distance',
      header: '거리',
      sortable: true,
      sortValue: (item) => item.distance_m ?? 0,
      cell: (item) => (item.distance_m === null ? '—' : `${Math.round(item.distance_m)}m`),
      align: 'right',
    },
  ];

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQ(queryInput.trim());
    setSelectedId(null);
  };

  return (
    <AdminPage
      title="Dedup review"
      description="kor-travel-map record linkage 후보 조회"
      actions={
        <button
          type="button"
          onClick={() => void reviewsQuery.refetch()}
          className="inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm"
          data-testid="admin-dedup-refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          갱신
        </button>
      }
    >
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-dedup-search" className="text-xs text-muted">
            검색
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2 h-4 w-4 text-muted" />
            <input
              id="admin-dedup-search"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className={`${inputClass} w-56 pl-7`}
              placeholder="feature, provider..."
              data-testid="admin-dedup-search"
            />
          </div>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-dedup-submit"
          >
            조회
          </button>
        </form>
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
          className={inputClass}
          data-testid="admin-dedup-status"
        >
          {STATUS_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <label className="text-xs text-muted" htmlFor="admin-dedup-min-score">
          min score
        </label>
        <input
          id="admin-dedup-min-score"
          value={minScore}
          onChange={(event) => setMinScore(event.target.value)}
          className={`${inputClass} w-20`}
          inputMode="numeric"
          data-testid="admin-dedup-min-score"
        />
        <span className="ml-auto text-xs text-muted">{data?.items.length ?? 0}행</span>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
        <AdminTable
          columns={columns}
          rows={data?.items ?? []}
          loading={reviewsQuery.isLoading}
          rowKey={(item) => item.review_id}
          rowTestId={(item) => `admin-dedup-row-${item.review_id}`}
          onRowClick={(item) => setSelectedId(item.review_id)}
          empty="dedup 후보가 없습니다."
        />
        <section
          className="space-y-4 rounded-sm border border-hairline bg-white p-4 text-sm"
          data-testid="admin-dedup-detail"
        >
          {selected ? (
            <>
              <div>
                <h2 className="text-sm font-semibold text-ink">{selected.review_id}</h2>
                <p className="text-xs text-muted">
                  total {score(selected.total_score)} / name {score(selected.name_score)} /
                  spatial {score(selected.spatial_score)}
                </p>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2">
                <dt className="text-muted">A</dt>
                <dd>{featureLabel(selected.feature_a)}</dd>
                <dt className="text-muted">B</dt>
                <dd>{featureLabel(selected.feature_b)}</dd>
                <dt className="text-muted">provider</dt>
                <dd>
                  {(selected.feature_a.provider ?? '—')}/{selected.feature_a.dataset_key ?? '—'} ·{' '}
                  {(selected.feature_b.provider ?? '—')}/{selected.feature_b.dataset_key ?? '—'}
                </dd>
                <dt className="text-muted">reviewed</dt>
                <dd>{formatDateTime(selected.reviewed_at)}</dd>
                <dt className="text-muted">reason</dt>
                <dd>{selected.decision_reason ?? '—'}</dd>
              </dl>
            </>
          ) : (
            <p className="text-muted">후보를 선택하면 양쪽 feature 요약이 표시됩니다.</p>
          )}
        </section>
      </section>
    </AdminPage>
  );
}
