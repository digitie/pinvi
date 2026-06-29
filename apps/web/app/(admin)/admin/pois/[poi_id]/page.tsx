'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import type {
  AdminAuditEntry,
  AdminOperationImpact,
  AdminOperationResult,
  AdminPoiDetail,
  AdminTripSummary,
} from '@pinvi/schemas';
import { Copy, MoveRight, Search, Trash2, X } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormTextArea } from '@/components/forms/FormTextArea';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const formatAmount = (value: string | null, currency: string) =>
  value === null ? '—' : `${value} ${currency}`;

const isBroken = (poi: AdminPoiDetail) => Boolean(poi.feature_link_broken_at);

type PoiOperationMode = 'poi_copy' | 'poi_move' | 'poi_delete';

const POI_OPERATION_LABELS: Record<PoiOperationMode, string> = {
  poi_copy: 'POI 복사',
  poi_move: 'POI 이동',
  poi_delete: 'POI 삭제',
};

const POI_OPERATION_MODES: { value: PoiOperationMode; label: string }[] = [
  { value: 'poi_copy', label: POI_OPERATION_LABELS.poi_copy },
  { value: 'poi_move', label: POI_OPERATION_LABELS.poi_move },
  { value: 'poi_delete', label: POI_OPERATION_LABELS.poi_delete },
];

const formatAffected = (affected: Record<string, number>) =>
  Object.entries(affected)
    .map(([key, value]) => `${key} ${value}`)
    .join(' / ');

const auditColumns: AdminTableColumn<AdminAuditEntry>[] = [
  {
    key: 'action',
    header: '액션',
    cell: (row) => <span className="font-mono text-xs">{row.action}</span>,
  },
  {
    key: 'access_reason',
    header: '사유',
    cell: (row) => row.access_reason ?? '—',
  },
  {
    key: 'occurred_at',
    header: '시각',
    sortable: true,
    sortValue: (row) => new Date(row.occurred_at).getTime(),
    cell: (row) => formatDateTime(row.occurred_at),
  },
];

function OperationImpactPanel({ impact }: { impact: AdminOperationImpact | null }) {
  if (!impact) {
    return <p className="text-sm text-muted">영향도를 불러오는 중...</p>;
  }

  return (
    <div className="space-y-3 rounded-sm border border-hairline bg-surface-soft p-3 text-sm">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">영향도</p>
        <p className="mt-1 text-ink">
          {Object.entries(impact.counts)
            .map(([key, value]) => `${key} ${value}`)
            .join(' / ') || '하위 항목 없음'}
        </p>
      </div>
      {Object.entries(impact.policy_options).map(([key, options]) => (
        <div key={key}>
          <p className="font-mono text-xs text-muted">{key}</p>
          <div className="mt-1 grid gap-1">
            {options.map((option) => (
              <p
                key={`${key}-${option.value}`}
                className={option.allowed ? 'text-ink' : 'text-muted'}
              >
                {option.allowed ? '허용' : '불가'} · {option.label}
                {option.reason ? ` · ${option.reason}` : ''}
              </p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AdminPoiDetailPage() {
  const router = useRouter();
  const params = useParams<{ poi_id: string }>();
  const poiId = params.poi_id;
  const [poi, setPoi] = useState<AdminPoiDetail | null>(null);
  const [brokenDraft, setBrokenDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [acting, setActing] = useState(false);
  const [showOperationDialog, setShowOperationDialog] = useState(false);
  const [operationMode, setOperationMode] = useState<PoiOperationMode>('poi_move');
  const [operationReason, setOperationReason] = useState('');
  const [operationError, setOperationError] = useState<string | null>(null);
  const [operationImpact, setOperationImpact] = useState<AdminOperationImpact | null>(null);
  const [operationResult, setOperationResult] = useState<AdminOperationResult | null>(null);
  const [targetTripQuery, setTargetTripQuery] = useState('');
  const [targetTrips, setTargetTrips] = useState<AdminTripSummary[]>([]);
  const [targetTripId, setTargetTripId] = useState('');
  const [targetDayIndex, setTargetDayIndex] = useState(1);
  const [includeAttachments, setIncludeAttachments] = useState(true);
  const [childPolicy, setChildPolicy] = useState<'move' | 'delete'>('move');

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getPoi(poiId)
      .then((res) => {
        if (cancelled) return;
        setPoi(res);
        setBrokenDraft(isBroken(res));
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/pois');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [poiId, router]);

  const refreshPoi = async () => {
    const updated = await adminApi(apiClient).getPoi(poiId);
    setPoi(updated);
    setBrokenDraft(isBroken(updated));
  };

  const openOperationDialog = (mode: PoiOperationMode) => {
    setOperationMode(mode);
    setOperationReason('');
    setOperationError(null);
    setOperationImpact(null);
    setOperationResult(null);
    setTargetTripQuery('');
    setTargetTrips([]);
    setTargetTripId(poi?.trip_id ?? '');
    setTargetDayIndex(poi?.day_index ?? 1);
    setIncludeAttachments(true);
    setChildPolicy('move');
    setShowOperationDialog(true);
  };

  useEffect(() => {
    if (!showOperationDialog) return;
    let cancelled = false;
    const q = targetTripQuery.trim();
    adminApi(apiClient)
      .listTrips({ page: 1, limit: 8, q: q || undefined })
      .then((res) => {
        if (cancelled) return;
        setTargetTrips(res.items);
        if (!targetTripId && res.items[0]) {
          setTargetTripId(res.items[0].trip_id);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setOperationError(err instanceof ApiError ? err.message : '대상 여행 검색 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [showOperationDialog, targetTripId, targetTripQuery]);

  useEffect(() => {
    if (!showOperationDialog) return;
    let cancelled = false;
    setOperationImpact(null);
    adminApi(apiClient)
      .getPoiOperationImpact(poiId)
      .then((impact) => {
        if (cancelled) return;
        setOperationImpact(impact);
      })
      .catch((err) => {
        if (cancelled) return;
        setOperationError(err instanceof ApiError ? err.message : '영향도 조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [poiId, showOperationDialog]);

  const onLinkStatusSave = async () => {
    if (!poi || reason.trim().length < 1) return;
    setActing(true);
    try {
      const updated = await adminApi(apiClient).updatePoiLinkStatus(poi.attachment_id, {
        broken: brokenDraft,
        access_reason: reason.trim(),
      });
      setPoi(updated);
      setBrokenDraft(isBroken(updated));
      setShowStatusDialog(false);
      setReason('');
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '연결 상태 변경 실패');
    } finally {
      setActing(false);
    }
  };

  const onOperationSave = async () => {
    if (!poi || operationReason.trim().length < 1) return;
    const access_reason = operationReason.trim();
    setActing(true);
    setOperationError(null);
    setOperationResult(null);
    try {
      let result: AdminOperationResult;
      if (operationMode === 'poi_copy') {
        result = await adminApi(apiClient).copyPoi(poi.attachment_id, {
          target_trip_id: targetTripId,
          target_day_index: targetDayIndex,
          include_attachments: includeAttachments,
          access_reason,
        });
      } else if (operationMode === 'poi_move') {
        result = await adminApi(apiClient).movePoi(poi.attachment_id, {
          target_trip_id: targetTripId,
          target_day_index: targetDayIndex,
          attachment_policy: childPolicy,
          comment_policy: childPolicy,
          access_reason,
        });
      } else {
        result = await adminApi(apiClient).deletePoi(poi.attachment_id, {
          attachment_policy: 'delete',
          comment_policy: 'delete',
          access_reason,
        });
      }
      setOperationResult(result);
      if (operationMode === 'poi_delete') {
        router.replace('/admin/pois');
        return;
      }
      await refreshPoi();
      setOperationReason('');
    } catch (err) {
      setOperationError(err instanceof ApiError ? err.message : '운영 작업 실패');
    } finally {
      setActing(false);
    }
  };

  if (error) {
    return (
      <AdminPage title="POI 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!poi) {
    return (
      <AdminPage title="POI 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  const currentBroken = isBroken(poi);
  const hasFeatureLink = poi.feature_id !== null;
  const featureTitle = poi.feature_label ?? poi.feature_id ?? 'Feature 없는 POI';
  const operationNeedsTarget = operationMode === 'poi_copy' || operationMode === 'poi_move';
  const operationConfirmDisabled =
    acting ||
    operationReason.trim().length < 1 ||
    (operationNeedsTarget && (!targetTripId || targetDayIndex < 1));

  return (
    <AdminPage
      title={featureTitle}
      description={`poi_id ${poi.attachment_id}`}
      actions={
        <Link href="/admin/pois" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-poi-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">여행</dt>
            <dd>
              <Link href={`/admin/trips/${poi.trip_id}`} className="text-primary underline">
                {poi.trip_title}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">소유자</dt>
            <dd className="font-mono">{poi.owner_email_masked}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">추가자</dt>
            <dd className="font-mono">{poi.added_by_email_masked ?? poi.added_by_user_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">일차 / 순서</dt>
            <dd>
              {poi.day_index}일차 / {poi.sort_order}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">feature_id</dt>
            <dd className="font-mono text-xs">{poi.feature_id ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">연결 상태</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              {hasFeatureLink ? (
                <>
                  <select
                    value={brokenDraft ? 'broken' : 'normal'}
                    onChange={(e) => setBrokenDraft(e.target.value === 'broken')}
                    className="rounded-sm border border-hairline px-2 py-1 text-sm"
                    data-testid="admin-poi-link-status"
                  >
                    <option value="normal">정상</option>
                    <option value="broken">끊김</option>
                  </select>
                  <button
                    type="button"
                    disabled={brokenDraft === currentBroken}
                    onClick={() => setShowStatusDialog(true)}
                    className="rounded-sm border border-primary px-3 py-1 text-sm text-primary disabled:opacity-50"
                    data-testid="admin-poi-link-status-save"
                  >
                    저장
                  </button>
                </>
              ) : (
                <span className="text-muted">—</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">끊김 시각</dt>
            <dd>{formatDateTime(poi.feature_link_broken_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">version</dt>
            <dd>{poi.version}</dd>
          </div>
        </dl>
      </Section>

      <Section title="운영 작업">
        <div className="flex flex-wrap gap-2" data-testid="admin-poi-operations">
          <button
            type="button"
            onClick={() => openOperationDialog('poi_copy')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-poi-copy-open"
          >
            <Copy className="h-4 w-4" aria-hidden="true" />
            POI 복사
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('poi_move')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-poi-move-open"
          >
            <MoveRight className="h-4 w-4" aria-hidden="true" />
            POI 이동
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('poi_delete')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-error-text px-3 text-sm text-error-text hover:bg-error-bg"
            data-testid="admin-poi-delete-open"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            POI 삭제
          </button>
        </div>
      </Section>

      <Section title="일정 / 비용">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">도착</dt>
            <dd>{formatDateTime(poi.planned_arrival_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">출발</dt>
            <dd>{formatDateTime(poi.planned_departure_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">예산</dt>
            <dd>{formatAmount(poi.budget_amount, poi.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">실사용</dt>
            <dd>{formatAmount(poi.actual_amount, poi.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">마커</dt>
            <dd>
              {poi.custom_marker_color ?? '—'} / {poi.custom_marker_icon ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">URL</dt>
            <dd className="break-all">{poi.user_url ?? '—'}</dd>
          </div>
        </dl>
        {poi.user_note && <p className="mt-4 text-sm text-ink">{poi.user_note}</p>}
      </Section>

      <Section title="Snapshot">
        <pre
          className="max-h-80 overflow-auto rounded-sm border border-hairline bg-surface-soft p-3 text-xs"
          data-testid="admin-poi-snapshot"
        >
          {JSON.stringify(poi.feature_snapshot, null, 2)}
        </pre>
      </Section>

      <Section title="최근 Audit">
        <div data-testid="admin-poi-audit-list">
          <AdminTable
            columns={auditColumns}
            rows={poi.recent_audit}
            rowKey={(row) => String(row.log_id)}
            empty="기록이 없습니다."
          />
        </div>
      </Section>

      {showOperationDialog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-poi-operation-title"
            className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-sm bg-white p-6 shadow-lg"
            data-testid="admin-poi-operation-dialog"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="admin-poi-operation-title" className="text-lg font-bold text-ink">
                  {POI_OPERATION_LABELS[operationMode]}
                </h3>
                <p className="mt-1 font-mono text-xs text-muted">{poi.attachment_id}</p>
              </div>
              <button
                type="button"
                onClick={() => setShowOperationDialog(false)}
                aria-label="닫기"
                className="flex h-10 w-10 items-center justify-center rounded-sm border border-hairline text-ink hover:bg-surface-soft"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="block text-xs uppercase tracking-wide text-muted">작업</span>
                <select
                  value={operationMode}
                  onChange={(e) => {
                    setOperationMode(e.target.value as PoiOperationMode);
                    setOperationResult(null);
                    setOperationError(null);
                  }}
                  className="w-full rounded-sm border border-hairline px-3 py-2"
                  data-testid="admin-poi-operation-mode"
                >
                  {POI_OPERATION_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>

              {operationNeedsTarget && (
                <label className="space-y-1 text-sm">
                  <span className="block text-xs uppercase tracking-wide text-muted">
                    대상 일차
                  </span>
                  <input
                    type="number"
                    min={1}
                    value={targetDayIndex}
                    onChange={(e) => setTargetDayIndex(Number(e.target.value))}
                    className="w-full rounded-sm border border-hairline px-3 py-2"
                    data-testid="admin-poi-operation-target-day"
                  />
                </label>
              )}

              {operationNeedsTarget && (
                <div className="space-y-2 md:col-span-2">
                  <label className="space-y-1 text-sm">
                    <span className="block text-xs uppercase tracking-wide text-muted">
                      대상 여행 검색
                    </span>
                    <span className="flex items-center gap-2 rounded-sm border border-hairline px-3 py-2">
                      <Search className="h-4 w-4 text-muted" aria-hidden="true" />
                      <input
                        value={targetTripQuery}
                        onChange={(e) => setTargetTripQuery(e.target.value)}
                        className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                        placeholder="여행 제목 또는 owner 검색"
                        data-testid="admin-poi-operation-target-search"
                      />
                    </span>
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="block text-xs uppercase tracking-wide text-muted">
                      대상 여행
                    </span>
                    <select
                      value={targetTripId}
                      onChange={(e) => setTargetTripId(e.target.value)}
                      className="w-full rounded-sm border border-hairline px-3 py-2"
                      data-testid="admin-poi-operation-target-trip"
                    >
                      {targetTrips.map((item) => (
                        <option key={item.trip_id} value={item.trip_id}>
                          {item.title} · {item.owner_email_masked}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}

              {operationMode === 'poi_copy' && (
                <label className="inline-flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={includeAttachments}
                    onChange={(e) => setIncludeAttachments(e.target.checked)}
                    data-testid="admin-poi-operation-include-attachments"
                  />
                  파일 포함
                </label>
              )}

              {operationMode === 'poi_move' && (
                <label className="space-y-1 text-sm">
                  <span className="block text-xs uppercase tracking-wide text-muted">
                    파일/댓글
                  </span>
                  <select
                    value={childPolicy}
                    onChange={(e) => setChildPolicy(e.target.value as 'move' | 'delete')}
                    className="w-full rounded-sm border border-hairline px-3 py-2"
                    data-testid="admin-poi-operation-policy"
                  >
                    <option value="move">대상으로 이동</option>
                    <option value="delete">함께 삭제</option>
                  </select>
                </label>
              )}

              <div className="md:col-span-2">
                <FormTextArea
                  id="admin-poi-operation-reason"
                  label="사유"
                  hint="감사 로그에 기록됩니다."
                  value={operationReason}
                  onChange={(e) => setOperationReason(e.target.value)}
                  rows={3}
                  data-testid="admin-poi-operation-reason"
                />
              </div>
            </div>

            <div className="mt-4">
              <OperationImpactPanel impact={operationImpact} />
            </div>

            {operationError && (
              <p
                className="mt-4 rounded-sm bg-error-bg p-3 text-sm text-error-text"
                data-testid="admin-poi-operation-error"
              >
                {operationError}
              </p>
            )}
            {operationResult && (
              <p
                className="mt-4 rounded-sm bg-success-bg p-3 text-sm text-success-text"
                data-testid="admin-poi-operation-result"
              >
                {operationResult.action} 완료 · {formatAffected(operationResult.affected)}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowOperationDialog(false)}
                className="rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                취소
              </button>
              <button
                type="button"
                disabled={operationConfirmDisabled}
                onClick={onOperationSave}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-poi-operation-confirm"
              >
                {acting ? '처리 중...' : '실행'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showStatusDialog && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-4 rounded-sm bg-white p-6">
            <h3 className="text-lg font-bold text-ink">POI 연결 상태 변경</h3>
            <p className="text-xs text-muted">
              {currentBroken ? '끊김' : '정상'} → {brokenDraft ? '끊김' : '정상'}
            </p>
            <FormTextArea
              id="admin-poi-action-reason"
              label="사유"
              hint="감사 로그에 기록됩니다."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              data-testid="admin-poi-action-reason"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowStatusDialog(false);
                  setReason('');
                }}
                className="rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                취소
              </button>
              <button
                type="button"
                disabled={acting || reason.trim().length < 1}
                onClick={onLinkStatusSave}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-poi-action-confirm"
              >
                {acting ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminPage>
  );
}
