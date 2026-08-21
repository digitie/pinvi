'use client';

import { useRef, useState, type MouseEvent } from 'react';
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

const formatDateTime = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const statusLabel = (status: string) => STATUS_LABELS[status] ?? status;
const actionLabel = (action: string) => ACTION_LABELS[action] ?? action;
const outcomeLabel = (outcome: string) => OUTCOME_LABELS[outcome] ?? outcome;

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

function EvidenceDetail({ detail }: { detail: AdminFeatureReferenceReconciliationDetail }) {
  const receipt = detail.receipt;
  return (
    <div className="space-y-4" data-testid="admin-frr-detail">
      <p
        role="status"
        className="rounded-sm border border-hairline bg-surface-soft px-3 py-2 text-sm text-body"
        data-testid="admin-frr-readonly-boundary"
      >
        이 화면은 읽기 전용입니다. Receipt, 관측 hash, 영향 행만 확인하고 상태 변경 작업은
        수행하지 않습니다.
      </p>

      <section aria-labelledby="admin-frr-conclusion-title" className="space-y-2">
        <h3 id="admin-frr-conclusion-title" className="text-sm font-semibold text-ink">
          결론
        </h3>
        <div className="rounded-sm border border-hairline bg-canvas p-3">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={detail.status} />
            <span className="text-sm text-body">
              {receipt
                ? `Map ACK가 확인되어 ${actionLabel(receipt.action)} 결론을 기록했습니다.`
                : 'blocked 관측으로 local mutation과 ACK를 중단했습니다.'}
            </span>
          </div>
          <p className="mt-2 break-all font-mono text-xs text-muted">event: {detail.event_id}</p>
        </div>
      </section>

      <section aria-labelledby="admin-frr-receipt-title" className="space-y-2">
        <h3 id="admin-frr-receipt-title" className="text-sm font-semibold text-ink">
          Receipt
        </h3>
        {receipt ? (
          <dl className="grid grid-cols-1 gap-2 rounded-sm border border-hairline bg-canvas p-3 text-sm sm:grid-cols-2">
            <dt className="text-muted">조치</dt>
            <dd>{actionLabel(receipt.action)}</dd>
            <dt className="text-muted">이전 Feature</dt>
            <dd className="break-all font-mono text-xs">{receipt.old_feature_id}</dd>
            <dt className="text-muted">대체 Feature</dt>
            <dd className="break-all font-mono text-xs">
              {receipt.replacement_feature_id ?? '—'}
            </dd>
            <dt className="text-muted">영향 행</dt>
            <dd>{receipt.impact_count}건</dd>
            <dt className="text-muted">Receipt SHA-256</dt>
            <dd className="break-all font-mono text-xs">{receipt.receipt_sha256}</dd>
          </dl>
        ) : (
          <p className="rounded-sm border border-error-text bg-error-bg p-3 text-sm text-error-text">
            Receipt가 없습니다. 아래 관측 hash로 block 원인을 확인하세요.
          </p>
        )}
      </section>

      <section aria-labelledby="admin-frr-attempts-title" className="space-y-2">
        <h3 id="admin-frr-attempts-title" className="text-sm font-semibold text-ink">
          관측
        </h3>
        <ul className="space-y-2">
          {detail.attempts.map((attempt) => (
            <li
              key={attempt.attempt_sequence}
              className="rounded-sm border border-hairline bg-canvas p-3 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-ink">#{attempt.attempt_sequence}</span>
                <StatusBadge status={attempt.status} />
                <span className="text-muted">{formatDateTime(attempt.observed_at)}</span>
              </div>
              {attempt.block_fingerprint_sha256 && (
                <p className="mt-2 break-all font-mono text-xs text-muted">
                  block: {attempt.block_fingerprint_sha256}
                </p>
              )}
              <p className="mt-1 break-all font-mono text-xs text-muted">
                observation: {attempt.observation_root_sha256}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="admin-frr-impacts-title" className="space-y-2">
        <h3 id="admin-frr-impacts-title" className="text-sm font-semibold text-ink">
          영향 행
        </h3>
        {detail.impacts.length > 0 ? (
          <ul className="space-y-2">
            {detail.impacts.map((impact) => (
              <li
                key={`${impact.target_relation}:${impact.target_id}`}
                className="rounded-sm border border-hairline bg-canvas p-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-ink">{impact.target_relation}</span>
                  <span className="text-muted">·</span>
                  <span>{outcomeLabel(impact.outcome)}</span>
                </div>
                <p className="mt-1 break-all font-mono text-xs text-muted">{impact.target_id}</p>
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
      <div className="flex items-start justify-between gap-3">
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
  });

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
  const closeDetail = () => setSelectedEventId(null);
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
      cell: (row) => <span className="font-mono text-xs">{row.event_id.slice(0, 12)}...</span>,
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
          <Button type="button" variant="secondary" size="md" onClick={() => void listQuery.refetch()}>
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
        returnFocusRef={detailReturnFocusRef}
        testId="admin-frr-detail-dialog"
      >
        {detailQuery.isLoading ? (
          <LoadingState label="증거 상세를 불러오는 중입니다." />
        ) : detailQuery.isError ? (
          <div role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
            증거 상세를 불러오지 못했습니다.
          </div>
        ) : detailQuery.data ? (
          <EvidenceDetail detail={detailQuery.data} />
        ) : null}
      </Dialog>
    </AdminPage>
  );
}
