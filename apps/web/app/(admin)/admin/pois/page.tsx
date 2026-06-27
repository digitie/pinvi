'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminPoiCreateRequest, AdminPoiSummary, AdminTripSummary } from '@pinvi/schemas';
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

const toKstIso = (value: string) => (value ? `${value}:00+09:00` : null);

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

function AdminPoiCreateDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tripQueryInput, setTripQueryInput] = useState('');
  const [tripQuery, setTripQuery] = useState('');
  const [selectedTrip, setSelectedTrip] = useState<AdminTripSummary | null>(null);
  const [dayIndex, setDayIndex] = useState('1');
  const [sortOrder, setSortOrder] = useState('a0');
  const [featureId, setFeatureId] = useState('');
  const [poiName, setPoiName] = useState('');
  const [addressLabel, setAddressLabel] = useState('');
  const [lon, setLon] = useState('');
  const [lat, setLat] = useState('');
  const [markerColor, setMarkerColor] = useState('');
  const [markerIcon, setMarkerIcon] = useState('');
  const [arrivalAt, setArrivalAt] = useState('');
  const [departureAt, setDepartureAt] = useState('');
  const [note, setNote] = useState('');
  const [budgetAmount, setBudgetAmount] = useState('');
  const [actualAmount, setActualAmount] = useState('');
  const [currency, setCurrency] = useState('KRW');
  const [userUrl, setUserUrl] = useState('');
  const [accessReason, setAccessReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const tripQueryResult = useQuery({
    queryKey: queryKeys.admin.trips({ page: 1, q: tripQuery }),
    queryFn: () => adminApi(apiClient).listTrips({ page: 1, limit: 8, q: tripQuery }),
    enabled: tripQuery.length > 0,
  });

  const createMutation = useMutation({
    mutationFn: (body: AdminPoiCreateRequest) => adminApi(apiClient).createPoi(body),
    onSuccess: (poi) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.all() });
      router.push(`/admin/pois/${poi.attachment_id}`);
    },
  });

  const onTripSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTripQuery(tripQueryInput.trim());
    setSelectedTrip(null);
  };

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedDay = Number.parseInt(dayIndex, 10);
    const trimmedSort = sortOrder.trim();
    const trimmedName = poiName.trim();
    const trimmedFeatureId = featureId.trim();
    const trimmedReason = accessReason.trim();
    const parsedLon = lon.trim() ? Number(lon) : null;
    const parsedLat = lat.trim() ? Number(lat) : null;
    if (!selectedTrip) {
      setFormError('여행계획을 선택하세요.');
      return;
    }
    if (!Number.isInteger(parsedDay) || parsedDay < 1) {
      setFormError('일차는 1 이상이어야 합니다.');
      return;
    }
    if (!trimmedSort) {
      setFormError('정렬 순서를 입력하세요.');
      return;
    }
    if (!trimmedName && !trimmedFeatureId) {
      setFormError('POI 이름 또는 feature_id를 입력하세요.');
      return;
    }
    if (Boolean(lon.trim()) !== Boolean(lat.trim())) {
      setFormError('좌표는 lon과 lat을 함께 입력하세요.');
      return;
    }
    if ((parsedLon !== null && Number.isNaN(parsedLon)) || (parsedLat !== null && Number.isNaN(parsedLat))) {
      setFormError('좌표는 숫자로 입력하세요.');
      return;
    }
    if (!trimmedReason) {
      setFormError('작업 사유를 입력하세요.');
      return;
    }

    const featureSnapshot: Record<string, unknown> = {};
    if (trimmedName) featureSnapshot.name = trimmedName;
    if (addressLabel.trim()) featureSnapshot.address_label = addressLabel.trim();
    if (parsedLon !== null && parsedLat !== null) {
      featureSnapshot.coord = { lon: parsedLon, lat: parsedLat };
    }

    const budget = budgetAmount.trim() ? Number(budgetAmount) : null;
    const actual = actualAmount.trim() ? Number(actualAmount) : null;
    if ((budget !== null && Number.isNaN(budget)) || (actual !== null && Number.isNaN(actual))) {
      setFormError('금액은 숫자로 입력하세요.');
      return;
    }

    setFormError(null);
    try {
      await createMutation.mutateAsync({
        trip_id: selectedTrip.trip_id,
        day_index: parsedDay,
        sort_order: trimmedSort,
        feature_id: trimmedFeatureId || null,
        feature_snapshot: featureSnapshot,
        custom_marker_color: markerColor.trim() || null,
        custom_marker_icon: markerIcon.trim() || null,
        planned_arrival_at: toKstIso(arrivalAt),
        planned_departure_at: toKstIso(departureAt),
        user_note: note.trim() || null,
        budget_amount: budget,
        actual_amount: actual,
        currency: currency.trim().toUpperCase(),
        user_url: userUrl.trim() || null,
        access_reason: trimmedReason,
      });
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'POI 생성 실패');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-poi-create-heading"
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-12"
      data-testid="admin-poi-create-dialog"
    >
      <div className="max-h-[calc(100vh-6rem)] w-full max-w-3xl overflow-auto rounded-sm bg-surface p-5 shadow-lg">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="admin-poi-create-heading" className="text-lg font-semibold text-ink">
              POI 생성
            </h2>
            <p className="mt-1 text-sm text-muted">여행계획과 일차를 지정합니다.</p>
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
            data-testid="admin-poi-create-error"
          >
            {formError}
          </p>
        )}

        <form onSubmit={onTripSearch} className="mb-4 flex flex-wrap items-end gap-2">
          <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
            <span className="text-xs text-muted">여행계획 검색</span>
            <input
              type="search"
              value={tripQueryInput}
              onChange={(event) => setTripQueryInput(event.target.value)}
              className="rounded-sm border border-hairline px-3 py-2"
              placeholder="제목, 지역, trip_id, owner"
              data-testid="admin-poi-trip-search"
            />
          </label>
          <button
            type="submit"
            className="rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="admin-poi-trip-search-submit"
          >
            검색
          </button>
        </form>

        {tripQuery.length > 0 && (
          <div className="mb-4 max-h-40 overflow-auto border-y border-hairline py-2">
            {tripQueryResult.isLoading && <p className="text-sm text-muted">검색 중...</p>}
            {tripQueryResult.data?.items.length === 0 && (
              <p className="text-sm text-muted">검색 결과 없음</p>
            )}
            <div className="grid gap-2">
              {tripQueryResult.data?.items.map((trip) => (
                <button
                  key={trip.trip_id}
                  type="button"
                  onClick={() => setSelectedTrip(trip)}
                  className="flex items-center justify-between gap-3 rounded-sm border border-hairline px-3 py-2 text-left text-sm"
                  data-testid={`admin-poi-trip-result-${trip.trip_id}`}
                >
                  <span>
                    <span className="font-medium text-ink">{trip.title}</span>
                    <span className="ml-2 text-muted">{trip.owner_email_masked}</span>
                  </span>
                  <span className="text-xs text-muted">{trip.status}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {selectedTrip && (
          <p className="mb-4 rounded-sm bg-surface-soft px-3 py-2 text-sm" data-testid="admin-poi-trip-selected">
            선택: {selectedTrip.title} · {selectedTrip.trip_id}
          </p>
        )}

        <form onSubmit={onCreate} className="grid gap-4">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">일차</span>
              <input
                type="number"
                min={1}
                value={dayIndex}
                onChange={(event) => setDayIndex(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-day"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">정렬 순서</span>
              <input
                value={sortOrder}
                onChange={(event) => setSortOrder(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                maxLength={80}
                data-testid="admin-poi-create-sort"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">feature_id</span>
              <input
                value={featureId}
                onChange={(event) => setFeatureId(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                maxLength={200}
                data-testid="admin-poi-create-feature-id"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">POI 이름</span>
              <input
                value={poiName}
                onChange={(event) => setPoiName(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-name"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">lon</span>
              <input
                inputMode="decimal"
                value={lon}
                onChange={(event) => setLon(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-lon"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">lat</span>
              <input
                inputMode="decimal"
                value={lat}
                onChange={(event) => setLat(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-lat"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm md:col-span-2">
              <span className="text-xs text-muted">주소</span>
              <input
                value={addressLabel}
                onChange={(event) => setAddressLabel(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-address"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">마커 색상</span>
              <input
                value={markerColor}
                onChange={(event) => setMarkerColor(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                placeholder="P-08"
                data-testid="admin-poi-create-marker-color"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">마커 아이콘</span>
              <input
                value={markerIcon}
                onChange={(event) => setMarkerIcon(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                maxLength={64}
                data-testid="admin-poi-create-marker-icon"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">도착</span>
              <input
                type="datetime-local"
                value={arrivalAt}
                onChange={(event) => setArrivalAt(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-arrival"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">출발</span>
              <input
                type="datetime-local"
                value={departureAt}
                onChange={(event) => setDepartureAt(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-departure"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">예산</span>
              <input
                inputMode="decimal"
                value={budgetAmount}
                onChange={(event) => setBudgetAmount(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-budget"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">실제 금액</span>
              <input
                inputMode="decimal"
                value={actualAmount}
                onChange={(event) => setActualAmount(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-actual"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">통화</span>
              <input
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2 uppercase"
                maxLength={3}
                data-testid="admin-poi-create-currency"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">URL</span>
              <input
                value={userUrl}
                onChange={(event) => setUserUrl(event.target.value)}
                className="rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-poi-create-url"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-muted">메모</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className="min-h-16 rounded-sm border border-hairline px-3 py-2"
              data-testid="admin-poi-create-note"
            />
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-xs text-muted">작업 사유</span>
            <textarea
              value={accessReason}
              onChange={(event) => setAccessReason(event.target.value)}
              className="min-h-16 rounded-sm border border-hairline px-3 py-2"
              maxLength={500}
              data-testid="admin-poi-create-reason"
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
              data-testid="admin-poi-create-submit"
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

export default function AdminPoisPage() {
  const [linkFilter, setLinkFilter] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [page, setPage] = useState(1);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

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
    <AdminPage
      title="POI"
      description="여행계획 POI 조회와 연결 상태 관리"
      actions={
        <button
          type="button"
          onClick={() => setShowCreateDialog(true)}
          className="inline-flex items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm text-white"
          data-testid="admin-poi-create-open"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          생성
        </button>
      }
    >
      {showCreateDialog && <AdminPoiCreateDialog onClose={() => setShowCreateDialog(false)} />}

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
