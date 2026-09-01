'use client';
// T-356 배선 단계 — 이 화면의 **수제 상태 배지**를 KTM admin idiom으로 갈아끼웠다.
// (KTM `src/components/status-badge.tsx` 이식본 소비처)
//
// 원문(= 전환 전 pinvi 코드)에서 바꾼 부분과 이유:
//  1) 로컬 `StatusBadge`(수제 `<span className="… rounded-full border …">` + blocked/applied
//     삼항 색 분기 + 수제 dot) → `@/components/admin/status-badge`의 `StatusBadge`.
//     dot·색·크기는 이제 badge recipe와 tone 테이블이 소유한다.
//  2) **문구·testid는 그대로다.** `data-testid="admin-frr-status-${status}"`는 live e2e
//     (`admin-feature-reference-reconciliations-live-mutating.live.ts`)가 잡고, '반영 완료'/'차단됨'은
//     `admin-feature-reference-reconciliations.e2e.ts`가 잡는다. 그래서 로컬 `STATUS_LABELS`를
//     계속 1순위 문구로 쓰고 `label` prop으로 넘긴다.
//     (공용 `lib/admin/status-label.ts`는 `applied`를 '반영됨'이라고 부른다 — 다르므로 쓰지 않았다.)
//  3) tone은 공용 테이블에서 그대로 읽힌다: `applied` → success, `blocked` → destructive.
//     전환 전 수제 색(성공=초록 / 차단=빨강)과 같은 의미라 `tone` prop을 강제하지 않았다.
//     스키마상 이 축은 `'blocked' | 'applied'` 둘뿐이라 fallback 경로가 실제로 돌지 않는다.
//  4) 로컬 헬퍼 `statusLabel`의 fallback만 `?? status`(raw enum) → 공용 `statusLabel()`로 바꿨다.
//     계약상 두 값밖에 없지만 upstream이 값을 늘려도 raw 영문이 화면에 새지 않는다.
//
// 보존한 것(계약): 모든 `data-testid`, '반영 완료'/'차단됨' 문구, 배지가 놓인 4곳
// (결론 헤더 · attempt 목록 · 모바일 카드 · 테이블 status 컬럼)과 그 순서·정렬 키.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type {
  AdminFeatureReferenceReconciliationDetail,
  AdminFeatureReferenceReconciliationSummary,
} from '@pinvi/schemas';
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterBar, FilterField } from '@/components/admin/filter-bar';
// T-356: 상세 모달을 사용자 표면 `components/ui/Dialog`(useModalDialog)에서 admin base-ui
// `Dialog`로 옮겼다. admin 화면에서는 두 모달 스택을 섞지 않는다. 본문의 `Button`(앱 공용)은
// 이번 작업 범위가 아니라 그대로 두고, 다이얼로그 닫기 버튼만 admin `Button`을 별칭으로 쓴다.
import { Button as AdminButton } from '@/components/admin/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/admin/ui/dialog';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';
import { Button } from '@/components/ui/Button';
// `isRestorableFocusTarget`은 모달 프리미티브가 아니라 순수 DOM 판별 헬퍼다 —
// 이 페이지가 breakpoint 전환 뒤 "지금 보이는 트리거"로 포커스를 되돌릴 때 계속 쓴다.
import { isRestorableFocusTarget } from '@/lib/useModalDialog';
import { StatusBadge as AdminStatusBadge } from '@/components/admin/status-badge';
import { statusLabel as sharedStatusLabel } from '@/lib/admin/status-label';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUS_FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'blocked', label: '차단' },
  { value: 'applied', label: '반영' },
] as const;

const STATUS_LABELS: Record<string, string> = {
  applied: '반영 완료',
  blocked: '차단됨',
};

const ACTION_LABELS: Record<string, string> = {
  rebind: '대체 Feature로 재연결',
  detach: '참조 분리',
};

const OUTCOME_LABELS: Record<string, string> = {
  rebind: '대체 Feature로 재연결',
  detach: '참조 분리',
  already_reconciled: '이미 조정됨',
};

const TARGET_RELATION_LABELS: Record<string, string> = {
  trip_day_pois: '여행 일정 POI',
  curated_plan_pois: '큐레이션 POI',
  feature_suggestions: 'Feature 제안',
};

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const statusLabel = (status: string) => STATUS_LABELS[status] ?? sharedStatusLabel(status);
const actionLabel = (action: string) => ACTION_LABELS[action] ?? action;
const outcomeLabel = (outcome: string) => OUTCOME_LABELS[outcome] ?? outcome;
const relationLabel = (relation: string) => TARGET_RELATION_LABELS[relation] ?? relation;

function findCurrentFocusTarget(focusReturnKey: string | null): HTMLElement | null {
  if (!focusReturnKey) return null;
  return (
    Array.from(document.querySelectorAll<HTMLElement>('[data-focus-return-key]')).find(
      (target) =>
        target.dataset.focusReturnKey === focusReturnKey && isRestorableFocusTarget(target),
    ) ?? null
  );
}

interface EvidenceField {
  label: string;
  field: string;
  value: ReactNode;
  mono?: boolean;
}

function ContractLabel({ label, field }: { label: string; field: string }) {
  return (
    <>
      {label} <span className="font-mono text-[11px] font-normal text-muted-soft">({field})</span>
    </>
  );
}

function EnumValue({ label, value }: { label: string; value: string }) {
  return (
    <span className="min-w-0">
      {label} <span className="font-mono text-xs text-muted">({value})</span>
    </span>
  );
}

function MonoValue({ value }: { value: string | number | null | undefined }) {
  const text = value == null || value === '' ? '—' : String(value);
  return <span className="break-all font-mono text-xs text-ink">{text}</span>;
}

function EvidenceFieldList({ items }: { items: EvidenceField[] }) {
  return (
    <dl className="grid min-w-0 grid-cols-1 gap-x-4 gap-y-3 text-sm sm:grid-cols-2">
      {items.map((item) => (
        <div key={`${item.field}:${item.label}`} className="min-w-0">
          <dt className="text-xs font-semibold text-muted">
            <ContractLabel label={item.label} field={item.field} />
          </dt>
          <dd
            className={`mt-1 min-w-0 text-ink [overflow-wrap:anywhere] ${
              item.mono ? 'break-all font-mono text-xs' : ''
            }`}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <AdminStatusBadge
      data-testid={`admin-frr-status-${status}`}
      label={statusLabel(status)}
      status={status}
    />
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      className="rounded-sm border border-hairline bg-surface-soft p-4 text-sm text-muted"
    >
      {label}
    </div>
  );
}

function DetailError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="space-y-3 rounded-sm bg-error-bg p-3 text-sm text-error-text">
      <p>증거 상세를 불러오지 못했습니다.</p>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={onRetry}
        data-testid="admin-frr-detail-retry"
      >
        다시 시도
      </Button>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="rounded-sm border border-hairline bg-surface-soft p-4 text-sm text-body">
      <h2 className="text-base font-semibold text-ink">표시할 조정 증거가 없습니다.</h2>
      <p className="mt-1 text-muted">
        상태 필터를 전체로 바꾸거나 Map M05 receipt 수집 이후 다시 확인하세요.
      </p>
    </section>
  );
}

function EvidenceDetail({
  detail,
  boundaryRef,
}: {
  detail: AdminFeatureReferenceReconciliationDetail;
  boundaryRef: RefObject<HTMLParagraphElement | null>;
}) {
  const receipt = detail.receipt;
  return (
    <div className="min-w-0 space-y-4" data-testid="admin-frr-detail">
      <p
        ref={boundaryRef}
        tabIndex={-1}
        role="status"
        // Tailwind v4에서 `outline-none`은 `--tw-outline-style: none`을 박고, `.focus-ring`의
        // `:focus-visible` 규칙은 스타일을 그 변수에서 읽는다 — 둘을 같이 두면 키보드 포커스 링이
        // 사라진다(v3에서는 `outline-none`이 투명 outline이라 공존이 가능했다). 최신 브라우저는
        // div/p의 프로그램적 focus에 `:focus-visible`을 매치하지 않아 기본 링도 그리지 않으므로
        // `outline-none` 없이 `.focus-ring`만 두는 것이 v4의 등가 동작이다.
        className="focus-ring rounded-sm bg-surface-soft px-3 py-2 text-sm text-body"
        data-testid="admin-frr-readonly-boundary"
      >
        이 화면은 읽기 전용입니다. 로컬 final receipt, delivery attempt 관측 hash, row-level
        impact만 확인하며 상태 변경 작업은 수행하지 않습니다.
      </p>

      <section aria-labelledby="admin-frr-conclusion-title" className="min-w-0 space-y-2">
        <h3 id="admin-frr-conclusion-title" className="text-sm font-semibold text-ink">
          결론
        </h3>
        <div className="min-w-0 rounded-sm bg-surface-soft p-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <StatusBadge status={detail.status} />
            <span className="min-w-0 text-sm text-body [overflow-wrap:anywhere]">
              {receipt
                ? `Map ACK가 확인되어 ${actionLabel(receipt.action)} 결론을 기록했습니다.`
                : '차단(blocked) 관측으로 local mutation과 Map ACK를 중단했습니다.'}
            </span>
          </div>
          <p className="mt-2 break-all font-mono text-xs text-muted">event_id: {detail.event_id}</p>
        </div>
      </section>

      <section
        aria-labelledby="admin-frr-receipt-title"
        className="min-w-0 space-y-3 border-t border-hairline pt-4"
      >
        <div className="min-w-0">
          <h3 id="admin-frr-receipt-title" className="text-sm font-semibold text-ink">
            로컬 final receipt
          </h3>
          <p className="mt-1 text-xs text-muted">
            Map ACK의 local_receipt_sha256이 참조하는 terminal local receipt입니다.
          </p>
        </div>
        {receipt ? (
          <EvidenceFieldList
            items={[
              {
                label: 'Event ID',
                field: 'event_id',
                value: <MonoValue value={receipt.event_id} />,
                mono: true,
              },
              { label: 'Event 순번', field: 'event_sequence', value: receipt.event_sequence },
              {
                label: 'Event SHA-256',
                field: 'event_sha256',
                value: <MonoValue value={receipt.event_sha256} />,
                mono: true,
              },
              {
                label: '조치',
                field: 'action',
                value: <EnumValue label={actionLabel(receipt.action)} value={receipt.action} />,
              },
              {
                label: '이전 Feature ID',
                field: 'old_feature_id',
                value: <MonoValue value={receipt.old_feature_id} />,
                mono: true,
              },
              {
                label: '이전 Feature UUID',
                field: 'old_feature_uuid',
                value: <MonoValue value={receipt.old_feature_uuid} />,
                mono: true,
              },
              {
                label: '대체 Feature ID',
                field: 'replacement_feature_id',
                value: <MonoValue value={receipt.replacement_feature_id} />,
                mono: true,
              },
              {
                label: '대체 Feature UUID',
                field: 'replacement_feature_uuid',
                value: <MonoValue value={receipt.replacement_feature_uuid} />,
                mono: true,
              },
              {
                label: '영향 root SHA-256',
                field: 'impact_root_sha256',
                value: <MonoValue value={receipt.impact_root_sha256} />,
                mono: true,
              },
              { label: '영향 행 수', field: 'impact_count', value: `${receipt.impact_count}건` },
              {
                label: 'Receipt SHA-256',
                field: 'receipt_sha256',
                value: <MonoValue value={receipt.receipt_sha256} />,
                mono: true,
              },
              {
                label: '적용 시각',
                field: 'applied_at',
                value: formatDateTime(receipt.applied_at),
              },
            ]}
          />
        ) : (
          <p className="rounded-sm border border-error-text bg-error-bg p-3 text-sm text-error-text">
            Receipt가 없습니다. 아래 차단 fingerprint와 관측 root hash로 중단 원인을 확인하세요.
          </p>
        )}
      </section>

      <section
        aria-labelledby="admin-frr-attempts-title"
        className="min-w-0 space-y-3 border-t border-hairline pt-4"
      >
        <h3 id="admin-frr-attempts-title" className="text-sm font-semibold text-ink">
          Delivery attempt 관측
        </h3>
        <ul className="space-y-3">
          {detail.attempts.map((attempt) => (
            <li
              key={attempt.attempt_sequence}
              className="min-w-0 rounded-sm border border-hairline bg-canvas p-3 text-sm"
            >
              <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
                <span className="font-semibold text-ink">시도 #{attempt.attempt_sequence}</span>
                <StatusBadge status={attempt.status} />
                <span className="text-muted">{formatDateTime(attempt.observed_at)}</span>
              </div>
              <EvidenceFieldList
                items={[
                  {
                    label: 'Event ID',
                    field: 'event_id',
                    value: <MonoValue value={attempt.event_id} />,
                    mono: true,
                  },
                  { label: 'Event 순번', field: 'event_sequence', value: attempt.event_sequence },
                  {
                    label: 'Event SHA-256',
                    field: 'event_sha256',
                    value: <MonoValue value={attempt.event_sha256} />,
                    mono: true,
                  },
                  {
                    label: '상태',
                    field: 'status',
                    value: <EnumValue label={statusLabel(attempt.status)} value={attempt.status} />,
                  },
                  {
                    label: '차단 fingerprint SHA-256',
                    field: 'block_fingerprint_sha256',
                    value: <MonoValue value={attempt.block_fingerprint_sha256} />,
                    mono: true,
                  },
                  {
                    label: '관측 root SHA-256',
                    field: 'observation_root_sha256',
                    value: <MonoValue value={attempt.observation_root_sha256} />,
                    mono: true,
                  },
                  {
                    label: '관측 시각',
                    field: 'observed_at',
                    value: formatDateTime(attempt.observed_at),
                  },
                ]}
              />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="admin-frr-impacts-title"
        className="min-w-0 space-y-3 border-t border-hairline pt-4"
      >
        <h3 id="admin-frr-impacts-title" className="text-sm font-semibold text-ink">
          Row-level impact
        </h3>
        {detail.impacts.length > 0 ? (
          <ul className="space-y-3">
            {detail.impacts.map((impact) => (
              <li
                key={`${impact.target_relation}:${impact.target_id}`}
                className="min-w-0 rounded-sm border border-hairline bg-canvas p-3 text-sm"
                data-testid={`admin-frr-impact-${impact.impact_index}`}
              >
                <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2">
                  <span className="font-semibold text-ink">
                    #{impact.impact_index + 1} {relationLabel(impact.target_relation)}
                  </span>
                  <span className="text-muted">·</span>
                  <span>{outcomeLabel(impact.outcome)}</span>
                </div>
                <EvidenceFieldList
                  items={[
                    {
                      label: 'Event ID',
                      field: 'event_id',
                      value: <MonoValue value={impact.event_id} />,
                      mono: true,
                    },
                    { label: 'Impact index', field: 'impact_index', value: impact.impact_index },
                    {
                      label: '대상 relation',
                      field: 'target_relation',
                      value: (
                        <EnumValue
                          label={relationLabel(impact.target_relation)}
                          value={impact.target_relation}
                        />
                      ),
                    },
                    {
                      label: '대상 ID',
                      field: 'target_id',
                      value: <MonoValue value={impact.target_id} />,
                      mono: true,
                    },
                    {
                      label: '이전 Feature ID',
                      field: 'old_feature_id',
                      value: <MonoValue value={impact.old_feature_id} />,
                      mono: true,
                    },
                    {
                      label: '이전 Feature UUID',
                      field: 'old_feature_uuid',
                      value: <MonoValue value={impact.old_feature_uuid} />,
                      mono: true,
                    },
                    {
                      label: '대체 Feature ID',
                      field: 'replacement_feature_id',
                      value: <MonoValue value={impact.replacement_feature_id} />,
                      mono: true,
                    },
                    {
                      label: '대체 Feature UUID',
                      field: 'replacement_feature_uuid',
                      value: <MonoValue value={impact.replacement_feature_uuid} />,
                      mono: true,
                    },
                    {
                      label: '결과',
                      field: 'outcome',
                      value: (
                        <EnumValue label={outcomeLabel(impact.outcome)} value={impact.outcome} />
                      ),
                    },
                    {
                      label: '기록 시각',
                      field: 'recorded_at',
                      value: formatDateTime(impact.recorded_at),
                    },
                  ]}
                />
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-sm border border-hairline bg-canvas p-3 text-sm text-muted">
            기록된 영향 행이 없습니다.
          </p>
        )}
      </section>
    </div>
  );
}

function MobileEvidenceCard({
  row,
  selected,
  onOpen,
}: {
  row: AdminFeatureReferenceReconciliationSummary;
  selected: boolean;
  onOpen: (
    event: MouseEvent<HTMLButtonElement>,
    row: AdminFeatureReferenceReconciliationSummary,
  ) => void;
}) {
  return (
    <article
      className="space-y-3 rounded-sm border border-hairline bg-canvas p-4"
      data-testid={`admin-frr-mobile-card-${row.event_id}`}
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <StatusBadge status={row.status} />
          <h2 className="mt-2 text-base font-semibold text-ink">이벤트 #{row.event_sequence}</h2>
          <p className="mt-1 break-all font-mono text-xs text-muted">{row.event_id}</p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="md"
          aria-haspopup="dialog"
          aria-expanded={selected}
          aria-label={`이벤트 #${row.event_sequence} 조정 증거 보기`}
          data-testid={`admin-frr-mobile-detail-${row.event_id}`}
          data-focus-return-key={row.event_id}
          onClick={(event) => onOpen(event, row)}
        >
          증거
        </Button>
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-muted">최근 관측</dt>
        <dd>#{row.latest_attempt.attempt_sequence}</dd>
        <dt className="text-muted">시각</dt>
        <dd>{formatDateTime(row.observed_at)}</dd>
        <dt className="text-muted">Receipt</dt>
        <dd>{row.receipt ? '있음' : '없음'}</dd>
      </dl>
    </article>
  );
}

export default function AdminFeatureReferenceReconciliationsPage() {
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]['value']>('all');
  const [page, setPage] = useState(1);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const detailReturnFocusRef = useRef<HTMLElement | null>(null);
  const detailReturnFocusKeyRef = useRef<string | null>(null);
  const pendingDetailFocusRestoreRef = useRef(false);
  const detailInitialFocusRef = useRef<HTMLParagraphElement | null>(null);
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
    retry: false,
  });

  useEffect(() => {
    if (selectedEventId !== null && detailQuery.data && detailInitialFocusRef.current) {
      detailInitialFocusRef.current.focus();
    }
  }, [detailQuery.data, selectedEventId]);

  const data = listQuery.data;
  const rows = data?.items ?? [];
  const error = listQuery.isError
    ? listQuery.error instanceof ApiError
      ? listQuery.error.message
      : '증거 목록을 불러오지 못했습니다.'
    : null;
  const openDetail = (
    event: MouseEvent<HTMLButtonElement>,
    row: AdminFeatureReferenceReconciliationSummary,
  ) => {
    detailReturnFocusRef.current = event.currentTarget;
    detailReturnFocusKeyRef.current = event.currentTarget.dataset.focusReturnKey ?? null;
    setSelectedEventId(row.event_id);
  };
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
    if (selectedEventId !== null || !pendingDetailFocusRestoreRef.current) return;
    pendingDetailFocusRestoreRef.current = false;
    focusAfterDialogTeardown(
      () => findCurrentFocusTarget(detailReturnFocusKeyRef.current) ?? detailReturnFocusRef.current,
    );
  }, [focusAfterDialogTeardown, selectedEventId]);
  const closeDetail = () => {
    pendingDetailFocusRestoreRef.current = true;
    setSelectedEventId(null);
  };
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
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'event_id',
      header: '이벤트',
      cell: (row) => (
        <span className="break-all font-mono text-xs" title={row.event_id}>
          {row.event_id.slice(0, 12)}...
        </span>
      ),
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
        <Button
          type="button"
          variant="secondary"
          size="md"
          aria-haspopup="dialog"
          aria-expanded={selectedEventId === row.event_id}
          aria-label={`이벤트 #${row.event_sequence} 조정 증거 보기`}
          data-testid={`admin-frr-detail-${row.event_id}`}
          data-focus-return-key={row.event_id}
          onClick={(event) => openDetail(event, row)}
        >
          증거
        </Button>
      ),
    },
  ];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  return (
    <AdminPage
      title="Feature 참조 조정 증거"
      description="Map M05 event의 append-only receipt, blocked 관측 및 영향 행을 읽기 전용으로 확인합니다."
    >
      {/*
        T-356 필터 툴바 전환 — `FormSelect`(라벨 + helper 슬롯 예약)를
        `FilterField` + `NativeSelect`로 바꿨다. 라벨 문구(`상태`)·`id`·`data-testid`·
        초기화 로직(page/selectedEventId)은 그대로다.
        `[&>select]:min-h-11`은 KTM `h-control`(36px) 대신 44px 터치 타깃을 유지하기 위한
        보정 — `admin-feature-reference-reconciliations.e2e.ts`가 320~768px에서
        `admin-frr-status-filter`의 높이 ≥ 44px를 검증한다.
      */}
      <FilterBar>
        <FilterField htmlFor="admin-frr-status" label="상태">
          <NativeSelect
            id="admin-frr-status"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value as (typeof STATUS_FILTERS)[number]['value']);
              setPage(1);
              setSelectedEventId(null);
            }}
            className="min-w-44 [&>select]:min-h-11"
            data-testid="admin-frr-status-filter"
          >
            {STATUS_FILTERS.map((filter) => (
              <NativeSelectOption key={filter.value} value={filter.value}>
                {filter.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </FilterField>
      </FilterBar>

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-sm bg-error-bg p-3 text-sm text-error-text"
        >
          <span>{error}</span>
          <Button
            type="button"
            variant="secondary"
            size="md"
            onClick={() => void listQuery.refetch()}
          >
            다시 시도
          </Button>
        </div>
      )}

      {!listQuery.isLoading && rows.length === 0 ? (
        <EmptyState />
      ) : (
        <AdminTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.event_id}
          loading={listQuery.isLoading}
          empty="아직 Map Feature 참조 조정 증거가 없습니다. 상태 필터를 전체로 바꿔 보세요."
          rowTestId={(row) => `admin-frr-row-${row.event_id}`}
          mobileCard={(row) => (
            <MobileEvidenceCard
              row={row}
              selected={selectedEventId === row.event_id}
              onOpen={openDetail}
            />
          )}
        />
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Button
          type="button"
          variant="secondary"
          size="md"
          disabled={page <= 1}
          onClick={() => setPage((current) => current - 1)}
          data-testid="admin-frr-prev-page"
        >
          이전
        </Button>
        <span className="text-muted" aria-live="polite">
          {page} / {totalPages} · {total}건
        </span>
        <Button
          type="button"
          variant="secondary"
          size="md"
          disabled={page >= totalPages}
          onClick={() => setPage((current) => current + 1)}
          data-testid="admin-frr-next-page"
        >
          다음
        </Button>
      </div>

      {/* 조건부 마운트 — 열림/닫힘 상태 소유자는 그대로 `selectedEventId`다. 닫힘 트랜지션
          동안 `detailQuery.data`가 사라져 본문이 빈칸으로 깜빡이는 것도 함께 막는다.
          접근성 이름은 `DialogTitle` 텍스트가 준다(e2e의 getByRole('dialog', { name: … })). */}
      {selectedEventId !== null && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) closeDetail();
          }}
        >
          <DialogContent
            className="max-w-3xl"
            data-testid="admin-frr-detail-dialog"
            initialFocus={detailInitialFocusRef}
          >
            <DialogHeader>
              <div className="min-w-0">
                <DialogTitle>Feature 참조 조정 증거 상세</DialogTitle>
                <DialogDescription className="mt-1">
                  Receipt, 관측, 영향 행을 확인하는 읽기 전용 M05 상세입니다.
                </DialogDescription>
              </div>
              <AdminButton
                type="button"
                variant="ghost"
                size="sm"
                onClick={closeDetail}
                data-testid="admin-frr-detail-dialog-close"
              >
                닫기
              </AdminButton>
            </DialogHeader>
            <div className="p-4">
              {detailQuery.isLoading ? (
                <LoadingState label="증거 상세를 불러오는 중입니다." />
              ) : detailQuery.isError ? (
                <DetailError onRetry={() => void detailQuery.refetch()} />
              ) : detailQuery.data ? (
                <EvidenceDetail detail={detailQuery.data} boundaryRef={detailInitialFocusRef} />
              ) : null}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </AdminPage>
  );
}
