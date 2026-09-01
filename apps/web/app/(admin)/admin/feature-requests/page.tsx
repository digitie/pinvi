'use client';
// T-356 배선 단계 — 이 화면의 **수제 상태 배지**와 **수제 JSON `<pre>`**를 KTM admin idiom으로
// 갈아끼웠다. (KTM `src/components/status-badge.tsx` / `src/components/json-viewer.tsx` 이식본 소비처)
//
// 원문(= 전환 전 pinvi 코드)에서 바꾼 부분과 이유:
//  1) 로컬 `StatusBadge`(수제 `<span className="… rounded-full border …">` + `STATUS_BADGE_CLASS`
//     색 테이블) → `@/components/admin/status-badge`의 `StatusBadge`. 색 테이블은 지웠고
//     tone은 `lib/admin/status-label.ts`의 tone 테이블이 정본이 된다.
//  2) **문구는 기존 것을 그대로 쓴다.** 이 페이지의 `STATUS_LABEL`(대기/승인/반영/중복/거절)이
//     화면 문구이자 `sortValue` 계약이라 `label` prop으로 넘겨 한 글자도 바꾸지 않았다.
//     공용 `statusLabel()`은 **fallback**으로만 쓴다 — 이 표에 없는 새 enum이 API에서 오면
//     raw 영문 대신 공용 한글 라벨이 나온다.
//  3) tone은 `STATUS_TONE`(아래)이 정본이고, 없으면 `toneFor()`로 떨어진다. 공용 tone 테이블에
//     `approved`/`added`/`duplicate` 키가 없어(= neutral로 떨어져 승인/반영이 회색이 된다)
//     여기서 명시했다. `pending`만 색이 실제로 바뀐다(회색 → warning): 공용 테이블이
//     "pending = 사람의 결정 대기 = warning"으로 못박고 있고 이 페이지의 기본 필터가 pending이다.
//  4) 수제 `<pre className="mt-2 max-h-48 … bg-surface-soft">` → `JsonViewer maxHeight="sm"`.
//     `max-h-48`(12rem)은 JsonViewer 3단 스케일(sm 10rem / md 18rem / lg 32rem)에 없어 가까운
//     `sm`으로 내렸다 — 런타임 값으로 `max-h-[…]`를 조립하지 않는다는 규칙 때문에 중간값을
//     새로 만들지 않았다. `<details>`/`<summary>`와 `admin-fr-map-ref-json-summary` testid는 그대로다.
//
// 보존한 것(계약): 모든 `data-testid`, `STATUS_LABEL` 문자열, `STATUS_FILTERS` option 텍스트·value,
// status 컬럼의 `sortValue`(라벨 기준 정렬), 나머지 문구·role.

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
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterBar, FilterField } from '@/components/admin/filter-bar';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';
import { FormField } from '@/components/forms/FormField';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { Button, ButtonLink } from '@/components/ui/Button';
// T-356: 검토 모달을 사용자 표면 `components/ui/Dialog`/`ConfirmDialog`(useModalDialog)에서
// admin base-ui 프리미티브로 옮겼다. 되돌릴 수 없는 **거절 확정**은 KTM 규약대로
// `AlertDialog`다(scrim 클릭으로는 닫히지 않는다 — base-ui가 alertdialog에서 강제로 끈다).
// 본문의 `Button`(앱 공용)은 이번 범위가 아니라 그대로 두고, 닫기 버튼만 admin `Button` 별칭.
import { Button as AdminButton } from '@/components/admin/ui/button';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from '@/components/admin/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/admin/ui/dialog';
// `isRestorableFocusTarget`은 모달 프리미티브가 아니라 순수 DOM 판별 헬퍼다 — breakpoint가
// 바뀐 뒤 "지금 보이는 트리거"로 포커스를 되돌리는 이 페이지 로직이 계속 쓴다.
import { isRestorableFocusTarget } from '@/lib/useModalDialog';
import { JsonViewer } from '@/components/admin/json-viewer';
import { StatusBadge as AdminStatusBadge } from '@/components/admin/status-badge';
import {
  statusLabel as sharedStatusLabel,
  toneFor,
  type StatusTone,
} from '@/lib/admin/status-label';

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

/**
 * status → tone. 공용 tone 테이블(`lib/admin/status-label.ts`)에 이 도메인 enum 중
 * `approved`/`added`/`duplicate`가 없어 여기서 명시한다(없으면 전부 neutral로 떨어진다).
 * `pending`/`rejected`는 공용 테이블과 같은 값이라 적지 않아도 되지만, 다섯 값을 한자리에
 * 모아 두는 편이 이 화면의 색 의미를 읽기 쉬워 함께 적었다.
 */
const STATUS_TONE: Record<string, StatusTone> = {
  pending: 'warning',
  approved: 'success',
  added: 'success',
  duplicate: 'neutral',
  rejected: 'destructive',
};

/** 화면 문구: 이 페이지의 표가 1순위, 없으면 공용 한글 라벨, 그래도 없으면 원문. */
const statusText = (status: string) => STATUS_LABEL[status] ?? sharedStatusLabel(status);

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

function findCurrentFocusTarget(focusReturnKey: string | null): HTMLElement | null {
  if (!focusReturnKey) return null;
  return (
    Array.from(document.querySelectorAll<HTMLElement>('[data-focus-return-key]')).find(
      (target) =>
        target.dataset.focusReturnKey === focusReturnKey && isRestorableFocusTarget(target),
    ) ?? null
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <AdminStatusBadge
      label={statusText(status)}
      status={status}
      tone={STATUS_TONE[status] ?? toneFor(status)}
    />
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
        <JsonViewer className="mt-2" maxHeight="sm" value={mapRef} />
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
          data-focus-return-key={request.request_id}
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
  // 파괴적 확인의 기본 포커스는 '계속 검토'(안전한 쪽)다 — 전환 전 ConfirmDialog와 같은 계약.
  const rejectCancelRef = useRef<HTMLButtonElement | null>(null);
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
    // `open`은 상수 true — 열림/닫힘은 계속 호출부의 `selected`가 소유한다.
    <Dialog
      open
      onOpenChange={(open) => {
        // 진행 중(busy)에는 Escape/scrim으로 닫히지 않는다 — 전환 전 `busy` 계약 그대로.
        if (!open && !busy) onClose();
      }}
    >
      <DialogContent
        className="max-w-3xl"
        data-testid="admin-fr-review-dialog"
        initialFocus={reasonRef}
        finalFocus={returnFocusRef}
      >
        <DialogHeader>
          <div className="min-w-0">
            <DialogTitle>
              {request.name}{' '}
              <span className="font-normal text-muted">
                ({TYPE_LABEL[request.type] ?? request.type})
              </span>
            </DialogTitle>
            <DialogDescription className="mt-1">
              제안 원문을 확인하고 승인 또는 거절 사유를 남깁니다.
            </DialogDescription>
          </div>
          <AdminButton
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={busy}
            data-testid="admin-fr-review-dialog-close"
          >
            닫기
          </AdminButton>
        </DialogHeader>
        {/* 본문만 스크롤한다(KTM request-dialog와 같은 레시피) — 320px에서도 root가 가로로
          밀리지 않아야 한다(e2e `expectNoRootHorizontalScroll`). */}
        <section
          className="max-h-[65vh] space-y-4 overflow-y-auto p-4"
          data-testid="admin-fr-review-panel"
        >
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
        <DialogFooter>{footer}</DialogFooter>
      </DialogContent>
      {/* 되돌릴 수 없는 거절 확정 — KTM 규약대로 AlertDialog(role=alertdialog). base-ui가
          alertdialog에서 scrim 클릭 닫기를 강제로 끄므로, 오조작으로 확인창이 사라지지 않는다.
          검토 Dialog 안에 중첩해 두어 base-ui가 두 모달의 스택 관계를 알게 한다. */}
      {rejectConfirmOpen && (
        <AlertDialog
          open
          onOpenChange={(open) => {
            if (!open && !rejectMutation.isPending) setRejectConfirmOpen(false);
          }}
        >
          <AlertDialogContent
            data-testid="admin-fr-reject-confirm"
            initialFocus={rejectCancelRef}
            finalFocus={rejectButtonRef}
          >
            <AlertDialogTitle>Feature 제안을 거절할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              거절하면 이 제안은 처리 완료 상태가 되고, 입력한 사유가 감사 기록에 남습니다.
            </AlertDialogDescription>
            <div
              className="mt-4 space-y-3 text-sm text-ink"
              data-testid="admin-fr-reject-confirmation"
            >
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
            <AlertDialogFooter>
              <AdminButton
                ref={rejectCancelRef}
                type="button"
                variant="outline"
                disabled={rejectMutation.isPending}
                onClick={() => {
                  if (!rejectMutation.isPending) setRejectConfirmOpen(false);
                }}
                data-testid="admin-fr-reject-confirm-cancel"
              >
                계속 검토
              </AdminButton>
              {/* design.md §CTA voice: destructive fill은 confirm dialog 안에서만 쓴다. */}
              <AdminButton
                type="button"
                variant="destructive-solid"
                disabled={rejectMutation.isPending}
                onClick={confirmReject}
                data-testid="admin-fr-reject-confirm-confirm"
              >
                거절 확정
              </AdminButton>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
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
  const reviewReturnFocusKeyRef = useRef<string | null>(null);
  const pendingReviewFocusRestoreRef = useRef(false);
  const noticeRef = useRef<HTMLParagraphElement | null>(null);
  const pendingNoticeFocusRef = useRef(false);

  const focusAfterDialogTeardown = useCallback((resolveTarget: () => HTMLElement | null) => {
    let remainingFrames = 8;
    const tryFocus = () => {
      const target = resolveTarget();
      if (target && isRestorableFocusTarget(target)) {
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
    focusAfterDialogTeardown(
      () => findCurrentFocusTarget(reviewReturnFocusKeyRef.current) ?? reviewReturnFocusRef.current,
    );
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
    reviewReturnFocusKeyRef.current = trigger.dataset.focusReturnKey ?? null;
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
      sortValue: (r) => statusText(r.status),
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
          data-focus-return-key={r.request_id}
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
      {/*
        T-356 필터 툴바 전환 — 옆에 붙여 두던 `<label>` + 수제 `<select>`를
        `FilterField`(라벨 위 · 컨트롤 아래) + `NativeSelect`로 바꿨다. 라벨 문구(`상태`),
        `id`, `data-testid`, `onChange` 배선은 그대로다.
        `[&>select]:min-h-11`은 KTM `h-control`(36px)이 pinvi의 44px 터치 타깃 게이트보다
        낮기 때문에 넣은 보정이다 — `admin-feature-requests.e2e.ts`가 320~768px에서
        `admin-fr-status-filter`의 boundingBox 높이 ≥ 44px를 검증한다. `NativeSelect`의
        `className`은 래퍼 div로 가므로 자식 `<select>`를 직접 가리킨다(정적 클래스).
      */}
      <FilterBar>
        <FilterField htmlFor="admin-fr-status" label="상태">
          <NativeSelect
            id="admin-fr-status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
              setSelected(null);
            }}
            className="min-w-36 [&>select]:min-h-11"
            data-testid="admin-fr-status-filter"
          >
            {STATUS_FILTERS.map((item) => (
              <NativeSelectOption key={item.value} value={item.value}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
        <span className="ml-auto text-xs text-muted">총 {total}건</span>
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
