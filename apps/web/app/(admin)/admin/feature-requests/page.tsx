'use client';

import { useState, type FormEvent } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminFeatureRequestSummary } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_FILTERS = [
  { value: 'pending', label: '대기' },
  { value: 'approved', label: '승인' },
  { value: 'added', label: '반영' },
  { value: 'rejected', label: '거절' },
  { value: '', label: '전체' },
];

const TYPE_LABEL: Record<string, string> = {
  new_place: '신규 장소',
  correction: '정보 수정',
  closure: '폐업',
};

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const inputClass = 'mt-0.5 w-full rounded-sm border border-hairline px-2 py-1 text-sm';

function ReviewPanel({
  request,
  onClose,
  onDone,
}: {
  request: AdminFeatureRequestSummary;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const isPending = request.status === 'pending';
  const isNewPlace = request.type === 'new_place';
  const [accessReason, setAccessReason] = useState('');
  const [category, setCategory] = useState('');
  const [markerColor, setMarkerColor] = useState('');
  const [markerIcon, setMarkerIcon] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const approveMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).approveFeatureRequest(request.request_id, {
        access_reason: accessReason.trim(),
        category: category.trim() || undefined,
        marker_color: markerColor.trim() || undefined,
        marker_icon: markerIcon.trim() || undefined,
      }),
    onSuccess: () => onDone('제안을 승인해 kor_travel_map에 전달했습니다.'),
    onError: (error) =>
      setErr(error instanceof ApiError ? error.message : '승인에 실패했습니다.'),
  });

  const rejectMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).rejectFeatureRequest(request.request_id, {
        access_reason: accessReason.trim(),
      }),
    onSuccess: () => onDone('제안을 거절했습니다.'),
    onError: (error) =>
      setErr(error instanceof ApiError ? error.message : '거절에 실패했습니다.'),
  });

  const busy = approveMutation.isPending || rejectMutation.isPending;

  const approve = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accessReason.trim()) {
      setErr('검토 사유를 입력하세요.');
      return;
    }
    if (isNewPlace && !(category.trim() && markerColor.trim() && markerIcon.trim())) {
      setErr('신규 장소 승인은 카테고리 코드 / 마커 색 / 마커 아이콘이 필요합니다.');
      return;
    }
    setErr(null);
    approveMutation.mutate();
  };

  const reject = () => {
    if (!accessReason.trim()) {
      setErr('검토 사유를 입력하세요.');
      return;
    }
    setErr(null);
    rejectMutation.mutate();
  };

  return (
    <section
      className="space-y-3 rounded-sm border border-hairline bg-surface-soft p-4"
      data-testid="admin-fr-review-panel"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">
          {request.name} <span className="text-muted">({TYPE_LABEL[request.type] ?? request.type})</span>
        </h2>
        <button type="button" onClick={onClose} className="text-xs text-muted hover:text-ink">
          닫기
        </button>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <dt className="text-muted">kind</dt>
        <dd>{request.kind}</dd>
        <dt className="text-muted">좌표</dt>
        <dd>
          {request.coord.lon}, {request.coord.lat}
        </dd>
        <dt className="text-muted">제안 카테고리</dt>
        <dd>{request.categories.join(', ') || '—'}</dd>
        <dt className="text-muted">대상 feature</dt>
        <dd>{request.target_feature_id ?? '—'}</dd>
        <dt className="text-muted">메모</dt>
        <dd>{request.note ?? '—'}</dd>
        <dt className="text-muted">요청자</dt>
        <dd>{request.requester_email_masked ?? '—'}</dd>
        <dt className="text-muted">상태</dt>
        <dd>{request.status}</dd>
      </dl>

      {request.kor_travel_map_ref && (
        <p className="break-all text-xs text-muted" data-testid="admin-fr-kor_travel_map-ref">
          kor_travel_map: {JSON.stringify(request.kor_travel_map_ref)}
        </p>
      )}

      {!isPending ? (
        <p className="text-xs text-muted">이미 처리된 제안입니다.</p>
      ) : (
        <form onSubmit={approve} className="space-y-2">
          {isNewPlace && (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <label className="block text-xs text-muted">
                카테고리 코드
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className={inputClass}
                  placeholder="01070100"
                  data-testid="admin-fr-category"
                />
              </label>
              <label className="block text-xs text-muted">
                마커 색
                <input
                  value={markerColor}
                  onChange={(e) => setMarkerColor(e.target.value)}
                  className={inputClass}
                  placeholder="P-07"
                  data-testid="admin-fr-marker-color"
                />
              </label>
              <label className="block text-xs text-muted">
                마커 아이콘
                <input
                  value={markerIcon}
                  onChange={(e) => setMarkerIcon(e.target.value)}
                  className={inputClass}
                  placeholder="cafe"
                  data-testid="admin-fr-marker-icon"
                />
              </label>
            </div>
          )}
          <label className="block text-xs text-muted">
            검토 사유 (audit 기록)
            <textarea
              value={accessReason}
              onChange={(e) => setAccessReason(e.target.value)}
              className={inputClass}
              rows={2}
              data-testid="admin-fr-reason"
            />
          </label>
          {err && (
            <p role="alert" className="text-xs text-error-text" data-testid="admin-fr-panel-error">
              {err}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-sm border border-hairline bg-ink px-3 py-1 text-sm text-white disabled:opacity-50"
              data-testid="admin-fr-approve"
            >
              승인
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={reject}
              className="rounded-sm border border-hairline px-3 py-1 text-sm disabled:opacity-50"
              data-testid="admin-fr-reject"
            >
              거절
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

export default function AdminFeatureRequestsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AdminFeatureRequestSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const featureRequestsQuery = useQuery({
    queryKey: queryKeys.admin.featureRequests({ status: statusFilter, page }),
    queryFn: () =>
      adminApi(apiClient).listFeatureRequests({
        status: statusFilter || undefined,
        page,
        limit: 50,
      }),
    placeholderData: keepPreviousData,
  });

  const data = featureRequestsQuery.data ?? null;
  const error = featureRequestsQuery.isError
    ? featureRequestsQuery.error instanceof ApiError
      ? featureRequestsQuery.error.message
      : '조회에 실패했습니다.'
    : null;

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  const columns: AdminTableColumn<AdminFeatureRequestSummary>[] = [
    {
      key: 'type',
      header: '유형',
      sortable: true,
      sortValue: (r) => TYPE_LABEL[r.type] ?? r.type,
      cell: (r) => TYPE_LABEL[r.type] ?? r.type,
    },
    { key: 'name', header: '이름', sortable: true, sortValue: (r) => r.name, cell: (r) => r.name },
    { key: 'kind', header: 'kind', cell: (r) => r.kind },
    {
      key: 'coord',
      header: '좌표',
      cell: (r) => `${r.coord.lon.toFixed(4)}, ${r.coord.lat.toFixed(4)}`,
    },
    { key: 'requester', header: '요청자', cell: (r) => r.requester_email_masked ?? '—' },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (r) => r.status,
      cell: (r) => r.status,
    },
    {
      key: 'created_at',
      header: '등록',
      sortable: true,
      sortValue: (r) => new Date(r.created_at).getTime(),
      cell: (r) => formatDateTime(r.created_at),
    },
    {
      key: 'action',
      header: '',
      cell: (r) => (
        <button
          type="button"
          onClick={() => {
            setSelected(r);
            setNotice(null);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-xs"
          data-testid={`admin-fr-review-${r.request_id}`}
        >
          검토
        </button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Feature 제안 검토"
      description="사용자 feature 제안을 검토해 kor_travel_map에 반영하거나 거절"
    >
      <FilterBar>
        <label htmlFor="admin-fr-status" className="text-xs text-muted">
          상태
        </label>
        <select
          id="admin-fr-status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
            setSelected(null);
          }}
          className="rounded-sm border border-hairline px-2 py-1 text-sm"
          data-testid="admin-fr-status-filter"
        >
          {STATUS_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted">총 {total}건</span>
      </FilterBar>

      {notice && (
        <p className="rounded-sm bg-surface-soft p-3 text-sm text-body" data-testid="admin-fr-notice">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text" data-testid="admin-fr-error">
          {error}
        </p>
      )}

      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        loading={featureRequestsQuery.isLoading}
        rowKey={(r) => r.request_id}
        rowTestId={(r) => `admin-fr-row-${r.request_id}`}
      />

      {selected && (
        <ReviewPanel
          request={selected}
          onClose={() => setSelected(null)}
          onDone={(message) => {
            setSelected(null);
            setNotice(message);
            void queryClient.invalidateQueries({ queryKey: queryKeys.admin.featureRequestsAll() });
          }}
        />
      )}

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
