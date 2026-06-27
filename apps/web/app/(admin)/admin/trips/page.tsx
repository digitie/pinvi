'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type {
  AdminTripCreateRequest,
  AdminTripSummary,
  AdminUserSummary,
  TripStatus,
  TripVisibility,
} from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
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

const CREATE_STATUSES: { value: TripStatus; label: string }[] = [
  { value: 'draft', label: '초안' },
  { value: 'planned', label: '계획' },
  { value: 'in_progress', label: '진행' },
  { value: 'completed', label: '완료' },
  { value: 'archived', label: '보관' },
];

const CREATE_VISIBILITIES: { value: TripVisibility; label: string }[] = [
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

const columns: AdminTableColumn<AdminTripSummary>[] = [
  {
    key: 'title',
    header: '여행',
    sortable: true,
    sortValue: (trip) => trip.title,
    cell: (trip) => (
      <Link href={`/admin/trips/${trip.trip_id}`} className="text-primary underline">
        {trip.title}
      </Link>
    ),
  },
  { key: 'owner', header: '소유자', cell: (trip) => trip.owner_email_masked },
  {
    key: 'status',
    header: '상태',
    sortable: true,
    sortValue: (trip) => trip.status,
    cell: (trip) => trip.status,
  },
  {
    key: 'visibility',
    header: '공개',
    sortable: true,
    sortValue: (trip) => trip.visibility,
    cell: (trip) => trip.visibility,
  },
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
    sortable: true,
    sortValue: (trip) => new Date(trip.updated_at).getTime(),
    cell: (trip) => new Date(trip.updated_at).toLocaleString('ko-KR'),
  },
];

function AdminTripCreateDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ownerQueryInput, setOwnerQueryInput] = useState('');
  const [ownerQuery, setOwnerQuery] = useState('');
  const [selectedOwner, setSelectedOwner] = useState<AdminUserSummary | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [regionHint, setRegionHint] = useState('');
  const [primaryRegionCode, setPrimaryRegionCode] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [visibility, setVisibility] = useState<TripVisibility>('private');
  const [status, setStatus] = useState<TripStatus>('draft');
  const [accessReason, setAccessReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const ownerQueryResult = useQuery({
    queryKey: queryKeys.admin.users({ page: 1, q: ownerQuery }),
    queryFn: () => adminApi(apiClient).listUsers({ page: 1, limit: 8, q: ownerQuery }),
    enabled: ownerQuery.length > 0,
  });

  const createMutation = useMutation({
    mutationFn: (body: AdminTripCreateRequest) => adminApi(apiClient).createTrip(body),
    onSuccess: (trip) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all() });
      router.push(`/admin/trips/${trip.trip_id}`);
    },
  });

  const onOwnerSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setOwnerQuery(ownerQueryInput.trim());
    setSelectedOwner(null);
  };

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const trimmedReason = accessReason.trim();
    if (!selectedOwner) {
      setFormError('소유자를 선택하세요.');
      return;
    }
    if (!trimmedTitle) {
      setFormError('여행계획명을 입력하세요.');
      return;
    }
    if (!trimmedReason) {
      setFormError('작업 사유를 입력하세요.');
      return;
    }
    if (Boolean(startDate) !== Boolean(endDate)) {
      setFormError('시작일과 종료일은 함께 입력하세요.');
      return;
    }
    setFormError(null);
    try {
      await createMutation.mutateAsync({
        owner_user_id: selectedOwner.user_id,
        title: trimmedTitle,
        description: description.trim() || null,
        region_hint: regionHint.trim() || null,
        primary_region_code: primaryRegionCode.trim() || null,
        start_date: startDate || null,
        end_date: endDate || null,
        visibility,
        status,
        access_reason: trimmedReason,
      });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : '여행계획 생성 실패');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-trip-create-heading"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-12"
      data-testid="admin-trip-create-dialog"
    >
      <div className="max-h-[calc(100vh-6rem)] w-full max-w-3xl overflow-auto rounded-sm bg-surface p-5 shadow-lg">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="admin-trip-create-heading" className="text-lg font-semibold text-ink">
              여행계획 생성
            </h2>
            <p className="mt-1 text-sm text-muted">소유자와 기본 정보를 지정합니다.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-hairline px-3 py-1 text-sm"
          >
            닫기
          </button>
        </div>

        {formError && (
          <p
            role="alert"
            className="mb-4 rounded-sm bg-error-bg p-3 text-sm text-error-text"
            data-testid="admin-trip-create-error"
          >
            {formError}
          </p>
        )}

        <form onSubmit={onOwnerSearch} className="mb-4 flex flex-wrap items-end gap-2">
          <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
            <span className="text-xs text-muted">소유자 검색</span>
            <input
              type="search"
              value={ownerQueryInput}
              onChange={(event) => setOwnerQueryInput(event.target.value)}
              className="rounded-sm border border-hairline px-3 py-2"
              placeholder="마스킹 이메일, 닉네임, user_id"
              data-testid="admin-trip-owner-search"
            />
          </label>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="admin-trip-owner-search-submit"
          >
            검색
          </button>
        </form>

        {ownerQuery.length > 0 && (
          <div className="mb-4 max-h-40 overflow-auto border-y border-hairline py-2">
            {ownerQueryResult.isLoading && <p className="text-sm text-muted">검색 중...</p>}
            {ownerQueryResult.data?.items.length === 0 && (
              <p className="text-sm text-muted">검색 결과 없음</p>
            )}
            <div className="grid gap-2">
              {ownerQueryResult.data?.items.map((user) => (
                <button
                  key={user.user_id}
                  type="button"
                  onClick={() => setSelectedOwner(user)}
                  className="flex items-center justify-between gap-3 rounded-sm border border-hairline px-3 py-2 text-left text-sm"
                  data-testid={`admin-trip-owner-result-${user.user_id}`}
                >
                  <span>
                    <span className="font-medium text-ink">
                      {user.nickname ?? user.email_masked}
                    </span>
                    <span className="ml-2 text-muted">{user.email_masked}</span>
                  </span>
                  <span className="text-xs text-muted">{user.status}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedOwner && (
          <p
            className="mb-4 rounded-sm bg-surface-soft px-3 py-2 text-sm"
            data-testid="admin-trip-owner-selected"
          >
            선택: {selectedOwner.nickname ?? selectedOwner.email_masked} · {selectedOwner.user_id}
          </p>
        )}

        <form onSubmit={onCreate} className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">여행계획명</span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                maxLength={200}
                data-testid="admin-trip-create-title"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">지역 힌트</span>
              <input
                value={regionHint}
                onChange={(event) => setRegionHint(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                maxLength={120}
                data-testid="admin-trip-create-region"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">행정구역 코드</span>
              <input
                value={primaryRegionCode}
                onChange={(event) => setPrimaryRegionCode(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                pattern="[0-9]{2,10}"
                data-testid="admin-trip-create-region-code"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">공개 범위</span>
              <select
                value={visibility}
                onChange={(event) => setVisibility(event.target.value as TripVisibility)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-trip-create-visibility"
              >
                {CREATE_VISIBILITIES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">상태</span>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value as TripStatus)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-trip-create-status"
              >
                {CREATE_STATUSES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">시작일</span>
              <input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-trip-create-start"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">종료일</span>
              <input
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-trip-create-end"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-muted">설명</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-20 rounded-sm border border-hairline px-3 py-2"
              data-testid="admin-trip-create-description"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-muted">작업 사유</span>
            <textarea
              value={accessReason}
              onChange={(event) => setAccessReason(event.target.value)}
              className="min-h-16 rounded-sm border border-hairline px-3 py-2"
              maxLength={500}
              data-testid="admin-trip-create-reason"
            />
          </label>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-sm border border-hairline px-3 py-2 text-sm"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="inline-flex items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-60"
              data-testid="admin-trip-create-submit"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              생성
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function AdminTripsPage() {
  const [statusFilter, setStatusFilter] = useState('');
  const [visibilityFilter, setVisibilityFilter] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const tripsQuery = useQuery({
    queryKey: queryKeys.admin.trips({
      page,
      status: statusFilter,
      visibility: visibilityFilter,
      q: submittedQuery,
    }),
    queryFn: () =>
      adminApi(apiClient).listTrips({
        page,
        limit: 50,
        status: statusFilter || undefined,
        visibility: visibilityFilter || undefined,
        q: submittedQuery || undefined,
      }),
    placeholderData: keepPreviousData,
  });

  const data = tripsQuery.data ?? null;
  const error = tripsQuery.isError
    ? tripsQuery.error instanceof ApiError
      ? tripsQuery.error.message
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
    <AdminPage
      title="여행"
      description="여행계획 조회와 운영 상태 관리"
      actions={
        <button
          type="button"
          onClick={() => setShowCreateDialog(true)}
          className="inline-flex items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm text-white"
          data-testid="admin-trip-create-open"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          생성
        </button>
      }
    >
      {showCreateDialog && <AdminTripCreateDialog onClose={() => setShowCreateDialog(false)} />}

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

      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        loading={tripsQuery.isLoading}
        rowKey={(trip) => trip.trip_id}
        rowTestId={(trip) => `admin-trips-row-${trip.trip_id}`}
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
