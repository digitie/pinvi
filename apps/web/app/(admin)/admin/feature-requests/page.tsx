'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { AdminFeatureRequestSummary } from '@pinvi/schemas';
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormField, inputClassName } from '@/components/forms/FormField';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { Button, ButtonLink } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Dialog } from '@/components/ui/Dialog';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_FILTERS = [
  { value: 'pending', label: '대기' },
  { value: 'approved', label: '승인' },
  { value: 'added', label: '반영' },
  { value: 'duplicate', label: '중복' },
  { value: 'rejected', label: '거절' },
  { value: '', label: '전체' },
];

const TYPE_LABEL: Record<string, string> = {
  new_place: '신규 장소',
  correction: '정보 수정',
  closure: '폐업',
};

const KIND_LABEL: Record<string, string> = {
  place: '장소',
  event: '이벤트',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '대기',
  approved: '승인',
  added: '반영',
  duplicate: '중복',
  rejected: '거절',
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  pending: 'border-hairline bg-surface-soft text-muted',
  approved: 'border-success-text bg-success-bg text-success-text',
  added: 'border-success-text bg-success-bg text-success-text',
  duplicate: 'border-hairline bg-surface-soft text-body',
  rejected: 'border-error-text bg-error-bg text-error-text',
};

const MAP_REF_LABEL: Record<string, string> = {
  review_mode: '검토 경로',
  request_id: '요청 ID',
  state: 'Map 상태',
  action: 'Map 액션',
  feature_id: 'Feature ID',
};

const MAP_REF_FIELDS = ['review_mode', 'request_id', 'state', 'action', 'feature_id'] as const;
const MAP_REF_FIELD_SET = new Set<string>(MAP_REF_FIELDS);
const DIALOG_LABEL_CLASS = 'block text-sm font-semibold text-ink';

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const formatCoord = (coord: AdminFeatureRequestSummary['coord']) =>
  `${coord.lon.toFixed(5)}, ${coord.lat.toFixed(5)}`;

const textFromUnknown = (value: unknown) => {
  if (value == null || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${
        STATUS_BADGE_CLASS[status] ?? 'border-hairline bg-surface-soft text-muted'
      }`}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function DetailGrid({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-4 gap-y-3 rounded-sm border border-hairline bg-surface-soft p-3 text-sm sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-xs font-semibold uppercase tracking-wide text-muted">{item.label}</dt>
          <dd className="mt-1 min-w-0 text-ink [overflow-wrap:anywhere]">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function MapReferencePanel({ request }: { request: AdminFeatureRequestSummary }) {
  const mapRef = request.kor_travel_map_ref;
  if (!mapRef) return null;

  const upstreamRequestId = typeof mapRef.request_id === 'string' ? mapRef.request_id : null;
  const reviewMode = typeof mapRef.review_mode === 'string' ? mapRef.review_mode : null;
  const primaryEntries = MAP_REF_FIELDS.filter((key) => mapRef[key] != null).map(
    (key) => [key, mapRef[key]] as const,
  );
  const extraEntries = Object.entries(mapRef).filter(([key]) => !MAP_REF_FIELD_SET.has(key));
  const entries = [...primaryEntries, ...extraEntries];

  return (
    <section
      className="rounded-sm border border-hairline bg-canvas p-3"
      data-testid="admin-fr-kor_travel_map-ref"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink">Map 전달 상태</h3>
          <p className="mt-1 text-xs text-muted">
            Feature 제안과 Map 검토 큐를 잇는 추적 값입니다.
          </p>
        </div>
        {upstreamRequestId && reviewMode !== 'feature_request_queue' ? (
          <ButtonLink
            href={`/admin/features/change-requests?q=${encodeURIComponent(upstreamRequestId)}`}
            variant="secondary"
            size="sm"
          >
            변경 요청 큐 보기
          </ButtonLink>
        ) : null}
      </div>

      {entries.length > 0 ? (
        <dl className="mt-3 grid grid-cols-1 gap-x-4 gap-y-3 border-t border-hairline pt-3 sm:grid-cols-2">
          {entries.map(([key, value]) => (
            <div key={key} className="min-w-0">
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                {MAP_REF_LABEL[key] ?? key}
              </dt>
              <dd className="mt-1 break-all text-sm text-ink">{textFromUnknown(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-3 rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
          전달 참조가 비어 있습니다.
        </p>
      )}

      {upstreamRequestId && reviewMode === 'feature_request_queue' ? (
        <p className="mt-3 rounded-sm bg-surface-soft px-3 py-2 text-sm text-body">
          Map Feature 요청 큐 ID: <span className="font-mono text-xs">{upstreamRequestId}</span>
        </p>
      ) : null}

      <details className="mt-3 text-sm text-muted">
        <summary
          className="focus-ring inline-flex min-h-11 cursor-pointer select-none items-center rounded-sm px-2 text-sm font-semibold text-ink underline-offset-2 hover:bg-surface-soft hover:underline"
          data-testid="admin-fr-map-ref-json-summary"
        >
          원본 JSON 보기
        </summary>
        <pre className="mt-2 max-h-48 overflow-auto rounded-sm bg-surface-soft p-3 text-xs leading-relaxed text-body">
          {JSON.stringify(mapRef, null, 2)}
        </pre>
      </details>
    </section>
  );
}

function FeatureRequestMobileCard({
  request,
  onReview,
}: {
  request: AdminFeatureRequestSummary;
  onReview: (trigger: HTMLElement) => void;
}) {
  return (
    <article
      className="rounded-sm border border-hairline bg-canvas p-4"
      data-testid={`admin-fr-mobile-card-${request.request_id}`}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">
            {TYPE_LABEL[request.type] ?? request.type}
          </p>
          <h2 className="mt-1 text-base font-semibold text-ink [overflow-wrap:anywhere]">
            {request.name}
          </h2>
        </div>
        <StatusBadge status={request.status} />
      </header>

      <dl className="mt-3 grid min-w-0 grid-cols-2 gap-2 text-sm">
        <div className="min-w-0">
          <dt className="text-xs text-muted">종류</dt>
          <dd className="mt-0.5 min-w-0 text-ink [overflow-wrap:anywhere]">
            {KIND_LABEL[request.kind] ?? request.kind}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted">등록</dt>
          <dd className="mt-0.5 min-w-0 text-ink [overflow-wrap:anywhere]">
            {formatDateTime(request.created_at)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted">좌표</dt>
          <dd className="mt-0.5 min-w-0 break-all font-mono text-xs text-ink">
            {formatCoord(request.coord)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted">요청자</dt>
          <dd className="mt-0.5 min-w-0 text-ink [overflow-wrap:anywhere]">
            {request.requester_email_masked ?? '—'}
          </dd>
        </div>
      </dl>

      <div className="mt-4 flex justify-end">
        <Button
          type="button"
          variant="secondary"
          size="md"
          aria-label={`${request.name} ${TYPE_LABEL[request.type] ?? request.type} 제안 검토 열기`}
          aria-haspopup="dialog"
          onClick={(event) => onReview(event.currentTarget)}
          data-testid={`admin-fr-mobile-review-${request.request_id}`}
        >
          검토
        </Button>
      </div>
    </article>
  );
}

function ReviewDialog({
  request,
  onClose,
  onDone,
  returnFocusRef,
}: {
  request: AdminFeatureRequestSummary;
  onClose: () => void;
  onDone: (message: string) => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  const isPending = request.status === 'pending';
  const isNewPlace = request.type === 'new_place';
  const isCorrection = request.type === 'correction';
  const formId = `admin-fr-review-form-${request.request_id}`;
  const reasonRef = useRef<HTMLTextAreaElement | null>(null);
  const rejectButtonRef = useRef<HTMLButtonElement | null>(null);
  const [accessReason, setAccessReason] = useState('');
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [markerColor, setMarkerColor] = useState('');
  const [markerIcon, setMarkerIcon] = useState('');
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [rejectConfirmOpen, setRejectConfirmOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const panelErrorRef = useRef<HTMLParagraphElement | null>(null);

  useEffect(() => {
    if (!err) return;
    panelErrorRef.current?.focus({ preventScroll: true });
  }, [err]);

  const approveMutation = useMutation({
    mutationFn: () => {
      const approval = {
        access_reason: accessReason.trim(),
        ...(isCorrection
          ? {
              name: name.trim() || undefined,
              category: category.trim() || undefined,
              marker_color: markerColor.trim() || undefined,
              marker_icon: markerIcon.trim() || undefined,
            }
          : {}),
      };
      return adminApi(apiClient).approveFeatureRequest(request.request_id, approval);
    },
    onSuccess: () =>
      onDone(
        isNewPlace
          ? '제안을 Map Feature 요청 큐에 제출했습니다.'
          : '제안을 승인해 kor_travel_map에 전달했습니다.',
      ),
    onError: (error) => {
      setRejectConfirmOpen(false);
      setErr(error instanceof ApiError ? error.message : '승인에 실패했습니다.');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: () =>
      adminApi(apiClient).rejectFeatureRequest(request.request_id, {
        access_reason: accessReason.trim(),
      }),
    onSuccess: () => onDone('제안을 거절했습니다.'),
    onError: (error) => {
      setRejectConfirmOpen(false);
      setErr(error instanceof ApiError ? error.message : '거절에 실패했습니다.');
    },
  });

  const busy = approveMutation.isPending || rejectMutation.isPending;

  const validateReason = () => {
    if (!accessReason.trim()) {
      setReasonError('검토 사유를 입력하세요.');
      setErr(null);
      reasonRef.current?.focus();
      return false;
    }
    setReasonError(null);
    return true;
  };

  const approve = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRejectConfirmOpen(false);
    if (!validateReason()) return;
    if (
      isCorrection &&
      !(name.trim() || category.trim() || markerColor.trim() || markerIcon.trim())
    ) {
      setErr('정보 수정 승인에는 이름, 카테고리, 마커 색 또는 마커 아이콘을 하나 이상 입력하세요.');
      return;
    }
    setErr(null);
    approveMutation.mutate();
  };

  const openRejectConfirm = () => {
    if (!validateReason()) return;
    setErr(null);
    setRejectConfirmOpen(true);
  };

  const confirmReject = () => {
    if (!validateReason()) {
      setRejectConfirmOpen(false);
      return;
    }
    setErr(null);
    rejectMutation.mutate();
  };

  const detailItems = [
    { label: '유형', value: TYPE_LABEL[request.type] ?? request.type },
    { label: '종류', value: KIND_LABEL[request.kind] ?? request.kind },
    {
      label: '좌표',
      value: <span className="font-mono text-xs">{formatCoord(request.coord)}</span>,
    },
    { label: '제안 카테고리', value: request.categories.join(', ') || '—' },
    { label: '대상 Feature', value: request.target_feature_id ?? '—' },
    { label: '요청자', value: request.requester_email_masked ?? '—' },
    { label: '상태', value: <StatusBadge status={request.status} /> },
    { label: '메모', value: request.note ?? '—' },
  ];

  const footer = !isPending ? (
    <Button type="button" variant="secondary" onClick={onClose}>
      닫기
    </Button>
  ) : (
    <>
      <Button type="button" variant="ghost" onClick={onClose} disabled={busy}>
        취소
      </Button>
      <Button
        ref={rejectButtonRef}
        type="button"
        variant="secondary"
        onClick={openRejectConfirm}
        disabled={approveMutation.isPending}
        loading={rejectMutation.isPending}
        state={err ? 'error' : 'idle'}
        data-testid="admin-fr-reject"
      >
        거절
      </Button>
      <Button
        type="submit"
        form={formId}
        loading={approveMutation.isPending}
        disabled={rejectMutation.isPending}
        state={err ? 'error' : 'idle'}
        data-testid="admin-fr-approve"
      >
        승인
      </Button>
    </>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      title={
        <>
          {request.name}{' '}
          <span className="font-normal text-muted">
            ({TYPE_LABEL[request.type] ?? request.type})
          </span>
        </>
      }
      description="제안 원문을 확인하고 승인 또는 거절 사유를 남깁니다."
      size="lg"
      variant="sheet"
      busy={busy}
      initialFocusRef={reasonRef}
      returnFocusRef={returnFocusRef}
      footer={footer}
      testId="admin-fr-review-dialog"
    >
      <section className="space-y-4" data-testid="admin-fr-review-panel">
        <DetailGrid items={detailItems} />
        <MapReferencePanel request={request} />

        {!isPending ? (
          <p className="rounded-sm bg-surface-soft p-3 text-sm text-muted">
            이미 처리된 제안입니다.
          </p>
        ) : (
          <form id={formId} onSubmit={approve} className="space-y-4">
            {isNewPlace && (
              <p
                className="rounded-sm border border-hairline bg-surface-soft p-3 text-sm text-body"
                data-testid="admin-fr-queue-payload-notice"
              >
                저장된 제안 내용 그대로 Map Feature 요청 큐에 제출합니다. 최종 분류와 마커는 Map
                검토자가 결정합니다.
              </p>
            )}

            {isCorrection && (
              <fieldset className="space-y-3 rounded-sm border border-hairline p-3">
                <legend className="px-1 text-sm font-semibold text-ink">수정 반영 필드</legend>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <FormField
                    id="admin-fr-name"
                    label="이름"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={request.name}
                    labelClassName={DIALOG_LABEL_CLASS}
                    data-testid="admin-fr-name"
                  />
                  <FormField
                    id="admin-fr-category"
                    label="카테고리 코드"
                    value={category}
                    onChange={(event) => setCategory(event.target.value)}
                    placeholder="01070100"
                    labelClassName={DIALOG_LABEL_CLASS}
                    data-testid="admin-fr-category"
                  />
                  <FormField
                    id="admin-fr-marker-color"
                    label="마커 색"
                    value={markerColor}
                    onChange={(event) => setMarkerColor(event.target.value)}
                    placeholder="P-07"
                    labelClassName={DIALOG_LABEL_CLASS}
                    data-testid="admin-fr-marker-color"
                  />
                  <FormField
                    id="admin-fr-marker-icon"
                    label="마커 아이콘"
                    value={markerIcon}
                    onChange={(event) => setMarkerIcon(event.target.value)}
                    placeholder="cafe"
                    labelClassName={DIALOG_LABEL_CLASS}
                    data-testid="admin-fr-marker-icon"
                  />
                </div>
              </fieldset>
            )}

            <FormTextArea
              ref={reasonRef}
              id="admin-fr-reason"
              label="검토 사유 (감사 기록)"
              value={accessReason}
              onChange={(event) => {
                setAccessReason(event.target.value);
                setRejectConfirmOpen(false);
                if (reasonError) setReasonError(null);
              }}
              rows={3}
              maxLength={500}
              error={reasonError ?? undefined}
              hint="승인/거절 모두 사유가 감사 기록에 남습니다."
              labelClassName={DIALOG_LABEL_CLASS}
              data-testid="admin-fr-reason"
            />

            {err && (
              <p
                ref={panelErrorRef}
                role="alert"
                tabIndex={-1}
                className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
                data-testid="admin-fr-panel-error"
              >
                {err}
              </p>
            )}
          </form>
        )}
      </section>
      <ConfirmDialog
        open={rejectConfirmOpen}
        title="Feature 제안을 거절할까요?"
        description="거절하면 이 제안은 처리 완료 상태가 되고, 입력한 사유가 감사 기록에 남습니다."
        confirmLabel="거절 확정"
        cancelLabel="계속 검토"
        tone="danger"
        busy={rejectMutation.isPending}
        onCancel={() => {
          if (!rejectMutation.isPending) setRejectConfirmOpen(false);
        }}
        onConfirm={confirmReject}
        returnFocusRef={rejectButtonRef}
        testId="admin-fr-reject-confirm"
      >
        <div className="space-y-3" data-testid="admin-fr-reject-confirmation">
          <p>“{request.name}” 제안을 거절합니다. 확정 전 검토 사유를 한 번 더 확인하세요.</p>
          <div className="rounded-sm border border-hairline bg-surface-soft p-3">
            <p className="text-xs font-semibold text-muted">거절 사유</p>
            <p
              className="mt-1 whitespace-pre-wrap text-sm text-ink [overflow-wrap:anywhere]"
              data-testid="admin-fr-reject-reason-preview"
            >
              {accessReason.trim()}
            </p>
          </div>
        </div>
      </ConfirmDialog>
    </Dialog>
  );
}

export default function AdminFeatureRequestsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('pending');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<AdminFeatureRequestSummary | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const reviewReturnFocusRef = useRef<HTMLElement | null>(null);
  const pendingReviewFocusRestoreRef = useRef(false);
  const noticeRef = useRef<HTMLParagraphElement | null>(null);
  const pendingNoticeFocusRef = useRef(false);

  const focusAfterDialogTeardown = useCallback((resolveTarget: () => HTMLElement | null) => {
    let remainingFrames = 8;
    const tryFocus = () => {
      const target = resolveTarget();
      if (
        target &&
        document.contains(target) &&
        !(target as HTMLElement & { disabled?: boolean }).disabled
      ) {
        target.closest('[inert]')?.removeAttribute('inert');
        target.focus({ preventScroll: true });
        return;
      }
      remainingFrames -= 1;
      if (remainingFrames > 0) window.requestAnimationFrame(tryFocus);
    };
    window.requestAnimationFrame(tryFocus);
  }, []);

  useEffect(() => {
    if (selected !== null || !pendingReviewFocusRestoreRef.current) return;
    pendingReviewFocusRestoreRef.current = false;
    focusAfterDialogTeardown(() => reviewReturnFocusRef.current);
  }, [focusAfterDialogTeardown, selected]);

  useEffect(() => {
    if (!notice || !pendingNoticeFocusRef.current) return;
    pendingNoticeFocusRef.current = false;
    focusAfterDialogTeardown(() => noticeRef.current);
  }, [focusAfterDialogTeardown, notice]);

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

  const openReview = (request: AdminFeatureRequestSummary, trigger: HTMLElement) => {
    reviewReturnFocusRef.current = trigger;
    setSelected(request);
    setNotice(null);
  };

  const closeReview = () => {
    pendingReviewFocusRestoreRef.current = true;
    setSelected(null);
  };

  const columns: AdminTableColumn<AdminFeatureRequestSummary>[] = [
    {
      key: 'type',
      header: '유형',
      sortable: true,
      sortValue: (r) => TYPE_LABEL[r.type] ?? r.type,
      cell: (r) => TYPE_LABEL[r.type] ?? r.type,
    },
    { key: 'name', header: '이름', sortable: true, sortValue: (r) => r.name, cell: (r) => r.name },
    { key: 'kind', header: '종류', cell: (r) => KIND_LABEL[r.kind] ?? r.kind },
    {
      key: 'coord',
      header: '좌표',
      cell: (r) => <span className="font-mono text-xs">{formatCoord(r.coord)}</span>,
    },
    { key: 'requester', header: '요청자', cell: (r) => r.requester_email_masked ?? '—' },
    {
      key: 'status',
      header: '상태',
      sortable: true,
      sortValue: (r) => STATUS_LABEL[r.status] ?? r.status,
      cell: (r) => <StatusBadge status={r.status} />,
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
        <Button
          type="button"
          variant="secondary"
          size="md"
          aria-label={`${r.name} ${TYPE_LABEL[r.type] ?? r.type} 제안 검토 열기`}
          aria-haspopup="dialog"
          onClick={(event) => openReview(r, event.currentTarget)}
          data-testid={`admin-fr-review-${r.request_id}`}
        >
          검토
        </Button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Feature 제안 검토"
      description="사용자 feature 제안을 검토해 Map 요청 큐 또는 변경 API에 전달하거나 거절"
    >
      <FilterBar>
        <label htmlFor="admin-fr-status" className="text-sm font-medium text-ink">
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
          className={inputClassName({ className: 'w-auto min-w-36' })}
          data-testid="admin-fr-status-filter"
        >
          {STATUS_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-sm text-muted">총 {total}건</span>
      </FilterBar>

      {notice && (
        <p
          ref={noticeRef}
          role="status"
          tabIndex={-1}
          className="focus-ring rounded-sm bg-surface-soft p-3 text-sm text-body"
          data-testid="admin-fr-notice"
        >
          {notice}
        </p>
      )}
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-fr-error"
        >
          <span>{error}</span>
          <Button
            type="button"
            variant="secondary"
            size="md"
            onClick={() => void featureRequestsQuery.refetch()}
            data-testid="admin-fr-retry"
          >
            다시 시도
          </Button>
        </div>
      )}

      <AdminTable
        columns={columns}
        rows={data?.items ?? []}
        loading={featureRequestsQuery.isLoading}
        empty="선택한 상태의 Feature 제안이 없습니다. 상태를 전체로 바꿔 처리 이력을 확인하세요."
        rowKey={(r) => r.request_id}
        rowTestId={(r) => `admin-fr-row-${r.request_id}`}
        mobileCard={(r) => (
          <FeatureRequestMobileCard request={r} onReview={(trigger) => openReview(r, trigger)} />
        )}
      />

      {selected && (
        <ReviewDialog
          request={selected}
          onClose={closeReview}
          returnFocusRef={reviewReturnFocusRef}
          onDone={(message) => {
            pendingNoticeFocusRef.current = true;
            setSelected(null);
            setNotice(message);
            void queryClient.invalidateQueries({ queryKey: queryKeys.admin.featureRequestsAll() });
            void queryClient.invalidateQueries({
              queryKey: queryKeys.admin.featureChangeRequestsAll(),
            });
          }}
        />
      )}

      <nav className="flex items-center justify-between text-sm" aria-label="Feature 제안 페이지">
        <Button
          type="button"
          variant="secondary"
          size="md"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          data-testid="admin-fr-prev-page"
        >
          이전
        </Button>
        <span className="text-muted" aria-live="polite">
          {page} / {totalPages}
        </span>
        <Button
          type="button"
          variant="secondary"
          size="md"
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          data-testid="admin-fr-next-page"
        >
          다음
        </Button>
      </nav>
    </AdminPage>
  );
}
