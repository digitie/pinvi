'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ApiClient, ApiError, adminApi } from '@tripmate/api-client';
import type { AdminTripPagedResponse, AdminTripSummary } from '@tripmate/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { DataTable, type DataTableColumn } from '@/components/admin/DataTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:9021',
});

const STATUSES = [
  { value: '', label: '전체' },
  { value: 'draft', label: '초안' },
  { value: 'planned', label: '계획' },
  { value: 'in_progress', label: '진행' },
  { value: 'completed', label: '완료' },
  { value: 'archived', label: '보관' },
];

const VISIBILITIES = [
  { value: '', label: '전체' },
  { value: 'private', label: 'private' },
  { value: 'unlisted', label: 'unlisted' },
  { value: 'public', label: 'public' },
];

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString('ko-KR') : '—';

const formatDateRange = (trip: AdminTripSummary) => {
  if (!trip.start_date && !trip.end_date) return '—';
  if (trip.start_date === trip.end_date) return formatDate(trip.start_date);
  return `${formatDate(trip.start_date)} ~ ${formatDate(trip.end_date)}`;
};

const columns: DataTableColumn<AdminTripSummary>[] = [
  {
    key: 'title',
    header: '여행',
    cell: (trip) => (
      <Link href={`/admin/trips/${trip.trip_id}`} className="text-primary underline">
        {trip.title}
      </Link>
    ),
  },
  { key: 'owner', header: '소유자', cell: (trip) => trip.owner_email_masked },
  { key: 'status', header: '상태', cell: (trip) => trip.status },
  { key: 'visibility', header: '공개', cell: (trip) => trip.visibility },
  {
    key: 'region',
    header: '지역',
    cell: (trip) => trip.region_hint ?? trip.primary_region_code ?? '—',
  },
  { key: 'period', header: '기간', cell: formatDateRange },
  {
    key: 'counts',
    header: '구성',
    cell: (trip) =>
      `D${trip.day_count} / POI ${trip.poi_count} / C${trip.companion_count} / S${trip.share_link_count}`,
  },
  {
    key: 'updated_at',
    header: '수정',
    cell: (trip) => new Date(trip.updated_at).toLocaleString('ko-KR'),
  },
];

export default function AdminTripsPage() {
  const [data, setData] = useState<AdminTripPagedResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    adminApi(apiClient)
      .listTrips({
        page,
        limit: 50,
        status: statusFilter || undefined,
        visibility: visibilityFilter || undefined,
        q: submittedQuery || undefined,
      })
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : '조회 실패');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [page, statusFilter, submittedQuery, visibilityFilter]);

  const total = data?.total ?? 0;
  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / 50)), [total]);

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQuery(queryInput.trim());
    setPage(1);
  };

  return (
    <AdminPage title="여행" description="여행계획 조회와 운영 상태 관리">
      <FilterBar>
        <form onSubmit={onSearch} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label htmlFor="admin-trips-search" className="text-xs text-muted">
            검색
          </label>
          <input
            id="admin-trips-search"
            type="search"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            className="min-w-56 rounded-sm border border-hairline px-2 py-1 text-sm"
            placeholder="제목, 지역, owner email, trip_id"
            data-testid="admin-trips-search"
          />
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
            data-testid="admin-trips-search-submit"
          >
            조회
          </button>
        </form>
        <label htmlFor="admin-trips-status-filter" className="text-xs text-muted">상태</label>
        <select
          id="admin-trips-status-filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-trips-status-filter"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <label htmlFor="admin-trips-visibility-filter" className="text-xs text-muted">공개</label>
        <select
          id="admin-trips-visibility-filter"
          value={visibilityFilter}
          onChange={(e) => {
            setVisibilityFilter(e.target.value);
            setPage(1);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-trips-visibility-filter"
        >
          {VISIBILITIES.map((v) => (
            <option key={v.value} value={v.value}>
              {v.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">총 {total}건</span>
      </FilterBar>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-trips-error"
        >
          {error}
        </p>
      )}

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        loading={loading}
        rowKey={(trip) => trip.trip_id}
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
