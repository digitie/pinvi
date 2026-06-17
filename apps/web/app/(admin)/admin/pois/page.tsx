'use client';

import Link from 'next/link';
import { useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminPoiSummary } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const LINK_FILTERS = [
  { value: '', label: '전체' },
  { value: 'false', label: '정상' },
  { value: 'true', label: '끊김' },
];

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const formatLinkStatus = (poi: AdminPoiSummary) =>
  poi.feature_link_broken_at ? `끊김 ${formatDateTime(poi.feature_link_broken_at)}` : '정상';

const columns: AdminTableColumn<AdminPoiSummary>[] = [
  {
    key: 'feature',
    header: 'POI',
    sortable: true,
    sortValue: (poi) => poi.feature_label ?? poi.feature_id ?? '',
    cell: (poi) => (
      <Link href={`/admin/pois/${poi.attachment_id}`} className="text-primary underline">
        {poi.feature_label ?? poi.feature_id}
      </Link>
    ),
  },
  {
    key: 'trip',
    header: '여행',
    sortable: true,
    sortValue: (poi) => poi.trip_title,
    cell: (poi) => (
      <Link href={`/admin/trips/${poi.trip_id}`} className="text-primary underline">
        {poi.trip_title}
      </Link>
    ),
  },
  { key: 'owner', header: '소유자', cell: (poi) => poi.owner_email_masked },
  {
    key: 'day',
    header: '일차',
    sortable: true,
    sortValue: (poi) => poi.day_index,
    cell: (poi) => `${poi.day_index}일차`,
  },
  {
    key: 'sort_order',
    header: '순서',
    sortable: true,
    sortValue: (poi) => poi.sort_order,
    cell: (poi) => poi.sort_order,
  },
  { key: 'feature_id', header: 'feature_id', cell: (poi) => poi.feature_id },
  { key: 'link', header: '연결', cell: formatLinkStatus },
  {
    key: 'updated_at',
    header: '수정',
    sortable: true,
    sortValue: (poi) => new Date(poi.updated_at).getTime(),
    cell: (poi) => formatDateTime(poi.updated_at),
  },
];

export default function AdminPoisPage() {
  const [linkFilter, setLinkFilter] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);

  const hasBrokenLink = linkFilter === '' ? undefined : linkFilter === 'true';

  const poisQuery = useQuery({
    queryKey: queryKeys.admin.pois({ page, hasBrokenLink, q: submittedQuery }),
    queryFn: () =>
      adminApi(apiClient).listPois({
        page,
        limit: 50,
        hasBrokenLink,
        q: submittedQuery || undefined,
      }),
    placeholderData: keepPreviousData,
  });

  const data = poisQuery.data ?? null;
  const error = poisQuery.isError
    ? poisQuery.error instanceof ApiError
      ? poisQuery.error.message
      : '조회 실패'
    : null;

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQuery(queryInput.trim());
    setPage(1);
  };

  return (
    <AdminPage title="POI" description="여행계획 POI 조회와 연결 상태 관리">
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-pois-search" className="text-xs text-muted">
            검색
          </label>
          <input
            id="admin-pois-search"
            type="search"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            className="min-w-56 rounded-sm border border-hairline px-2 py-1 text-sm"
            placeholder="feature_id, label, trip, owner email, poi_id"
            data-testid="admin-pois-search"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-pois-search-submit"
          >
            조회
          </button>
        </form>
        <label htmlFor="admin-pois-broken-filter" className="text-xs text-muted">연결</label>
        <select
          id="admin-pois-broken-filter"
          value={linkFilter}
          onChange={(e) => {
            setLinkFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-pois-broken-filter"
        >
          {LINK_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">총 {total}건</span>
      </FilterBar>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text" data-testid="admin-pois-error">
          {error}
        </p>
      )}

      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        loading={poisQuery.isLoading}
        rowKey={(poi) => poi.attachment_id}
        rowTestId={(poi) => `admin-pois-row-${poi.attachment_id}`}
      />

      <div className="flex items-center justify-between text-sm">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
        >
          이전
        </button>
        <span className="text-muted">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          className="rounded-sm border border-hairline px-3 py-1 disabled:opacity-50"
        >
          다음
        </button>
      </div>
    </AdminPage>
  );
}
