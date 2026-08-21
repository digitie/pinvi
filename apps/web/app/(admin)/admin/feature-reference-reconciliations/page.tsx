'use client';

import {
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
import { AdminPage, FilterBar } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormSelect } from '@/components/forms/FormSelect';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

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

const statusLabel = (status: string) => STATUS_LABELS[status] ?? status;
const actionLabel = (action: string) => ACTION_LABELS[action] ?? action;
const outcomeLabel = (outcome: string) => OUTCOME_LABELS[outcome] ?? outcome;
const relationLabel = (relation: string) => TARGET_RELATION_LABELS[relation] ?? relation;

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
  const blocked = status === 'blocked';
  return (
    <span
      className={`inline-flex min-h-6 items-center gap-1 rounded-full border px-2 text-xs font-semibold ${
        blocked
          ? 'border-error-text bg-error-bg text-error-text'
          : 'border-success-text bg-success-bg text-success-text'
      }`}
      data-testid={`admin-frr-status-${status}`}
    >
      <span
        aria-hidden="true"
        className={`size-1.5 rounded-full ${blocked ? 'bg-error-text' : 'bg-success-text'}`}
      />
      {statusLabel(status)}
    </span>
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
        className="focus-ring rounded-sm bg-surface-soft px-3 py-2 text-sm text-body outline-none"
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
    setSelectedEventId(row.event_id);
  };
  const focusAfterDialogTeardown = (resolveTarget: () => HTMLElement | null) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const target = resolveTarget();
        if (!target || !document.contains(target)) return;
        if ((target as HTMLElement & { disabled?: boolean }).disabled) return;
        target.closest('[inert]')?.removeAttribute('inert');
        target.focus({ preventScroll: true });
      });
    });
  };
  const closeDetail = () => {
    const trigger = detailReturnFocusRef.current;
    setSelectedEventId(null);
    focusAfterDialogTeardown(() => trigger);
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
      <FilterBar>
        <FormSelect
          id="admin-frr-status"
          label="상태"
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value as (typeof STATUS_FILTERS)[number]['value']);
            setPage(1);
            setSelectedEventId(null);
          }}
          className="min-w-44"
          data-testid="admin-frr-status-filter"
        >
          {STATUS_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>
              {filter.label}
            </option>
          ))}
        </FormSelect>
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

      <Dialog
        open={selectedEventId !== null}
        onClose={closeDetail}
        title="Feature 참조 조정 증거 상세"
        description="Receipt, 관측, 영향 행을 확인하는 읽기 전용 M05 상세입니다."
        size="lg"
        initialFocusRef={detailInitialFocusRef}
        returnFocusRef={detailReturnFocusRef}
        testId="admin-frr-detail-dialog"
      >
        {detailQuery.isLoading ? (
          <LoadingState label="증거 상세를 불러오는 중입니다." />
        ) : detailQuery.isError ? (
          <DetailError onRetry={() => void detailQuery.refetch()} />
        ) : detailQuery.data ? (
          <EvidenceDetail detail={detailQuery.data} boundaryRef={detailInitialFocusRef} />
        ) : null}
      </Dialog>
    </AdminPage>
  );
}
