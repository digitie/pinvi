'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import { paletteHex } from '@pinvi/domain';
import type {
  AdminAuditEntry,
  AdminOperationImpact,
  AdminOperationResult,
  AdminTripCompanionSummary,
  AdminTripDaySummary,
  AdminTripDetail,
  AdminTripPoiSummary,
  AdminTripShareLinkSummary,
  AdminTripSummary,
  AttachmentLibraryItem,
  TripStatus,
} from '@pinvi/schemas';
import { Copy, Download, ExternalLink, MapPin, MoveRight, Search, Trash2, X } from 'lucide-react';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormTextArea } from '@/components/forms/FormTextArea';
import {
  MakiMarker,
  MapFallback,
  MapLoadingSkeleton,
  Popup,
  VWorldMap,
} from '@/components/map/vworldPrimitives';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const STATUSES: { value: TripStatus; label: string }[] = [
  { value: 'draft', label: '초안' },
  { value: 'planned', label: '계획' },
  { value: 'in_progress', label: '진행' },
  { value: 'completed', label: '완료' },
  { value: 'archived', label: '보관' },
];

type TripOperationMode =
  | 'trip_copy'
  | 'trip_move'
  | 'trip_delete'
  | 'day_copy'
  | 'day_move'
  | 'day_delete';

const TRIP_OPERATION_LABELS: Record<TripOperationMode, string> = {
  trip_copy: '여행 복사',
  trip_move: '여행 소유자 이전',
  trip_delete: '여행 삭제',
  day_copy: '날짜 복사',
  day_move: '날짜 이동',
  day_delete: '날짜 삭제',
};

const OPERATION_MODES: { value: TripOperationMode; label: string }[] = [
  { value: 'trip_copy', label: TRIP_OPERATION_LABELS.trip_copy },
  { value: 'trip_move', label: TRIP_OPERATION_LABELS.trip_move },
  { value: 'trip_delete', label: TRIP_OPERATION_LABELS.trip_delete },
  { value: 'day_copy', label: TRIP_OPERATION_LABELS.day_copy },
  { value: 'day_move', label: TRIP_OPERATION_LABELS.day_move },
  { value: 'day_delete', label: TRIP_OPERATION_LABELS.day_delete },
];

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString('ko-KR') : '—';

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '—';

const formatAmount = (value: string | null, currency: string) =>
  value === null ? '—' : `${value} ${currency}`;

const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const formatAffected = (affected: Record<string, number>) =>
  Object.entries(affected)
    .map(([key, value]) => `${key} ${value}`)
    .join(' / ');

const attachmentScopeLabel: Record<AttachmentLibraryItem['target_scope'], string> = {
  trip: '여행',
  day: '날짜',
  poi: 'POI',
  curated_plan: '추천 계획',
  curated_poi: '추천 POI',
};

const formatDayLabel = (dayIndex: number, date: string | null, title: string | null) => {
  const prefix = `${dayIndex}일차`;
  const parts = [date ? formatDate(date) : null, title].filter(Boolean);
  return parts.length > 0 ? `${prefix} · ${parts.join(' · ')}` : prefix;
};

const companionColumns: AdminTableColumn<AdminTripCompanionSummary>[] = [
  {
    key: 'user',
    header: '사용자',
    cell: (row) =>
      row.user_id ? (
        <Link href={`/admin/users/${row.user_id}`} className="text-primary underline">
          {row.invited_email_masked ?? row.user_id}
        </Link>
      ) : (
        <span className="inline-flex items-center rounded-sm bg-surface-soft px-2 py-1 text-xs text-muted">
          미가입 초대
        </span>
      ),
  },
  {
    key: 'invited_email_masked',
    header: '초대 이메일',
    cell: (row) => <span className="font-mono text-xs">{row.invited_email_masked ?? '—'}</span>,
  },
  {
    key: 'invited_nickname',
    header: '닉네임',
    cell: (row) => row.invited_nickname ?? '—',
  },
  {
    key: 'role',
    header: '역할',
    cell: (row) => row.role,
  },
  {
    key: 'joined_at',
    header: '가입',
    sortable: true,
    sortValue: (row) => (row.joined_at ? new Date(row.joined_at).getTime() : 0),
    cell: (row) => formatDateTime(row.joined_at),
  },
  {
    key: 'invited_at',
    header: '초대',
    sortable: true,
    sortValue: (row) => new Date(row.invited_at).getTime(),
    cell: (row) => formatDateTime(row.invited_at),
  },
];

const dayColumns: AdminTableColumn<AdminTripDaySummary>[] = [
  {
    key: 'day_index',
    header: '일차',
    sortable: true,
    sortValue: (row) => row.day_index,
    cell: (row) => `${row.day_index}일차`,
  },
  {
    key: 'date',
    header: '날짜',
    sortable: true,
    sortValue: (row) => (row.date ? new Date(row.date).getTime() : 0),
    cell: (row) => formatDate(row.date),
  },
  {
    key: 'title',
    header: '제목',
    cell: (row) => row.title ?? '—',
  },
  {
    key: 'poi_count',
    header: 'POI',
    sortable: true,
    sortValue: (row) => row.poi_count,
    cell: (row) => row.poi_count,
  },
  {
    key: 'note',
    header: '메모',
    cell: (row) => row.note ?? '—',
  },
];

const poiColumns: AdminTableColumn<AdminTripPoiSummary>[] = [
  {
    key: 'day',
    header: '날짜',
    sortable: true,
    sortValue: (row) => row.day_index,
    cell: (row) => formatDayLabel(row.day_index, row.day_date, row.day_title),
  },
  {
    key: 'feature_label',
    header: 'POI',
    cell: (row) => (
      <span className="inline-flex items-center gap-2">
        <MapPin className="h-4 w-4 text-muted" aria-hidden="true" />
        <span>{row.feature_label ?? row.feature_id ?? 'Feature 없는 POI'}</span>
      </span>
    ),
  },
  {
    key: 'planned_arrival_at',
    header: '도착/출발',
    sortable: true,
    sortValue: (row) =>
      row.planned_arrival_at ? new Date(row.planned_arrival_at).getTime() : row.day_index,
    cell: (row) => `${formatTime(row.planned_arrival_at)} / ${formatTime(row.planned_departure_at)}`,
  },
  {
    key: 'sort_order',
    header: '순서',
    cell: (row) => <span className="font-mono text-xs">{row.sort_order}</span>,
  },
  {
    key: 'feature_link_broken_at',
    header: '연결',
    cell: (row) => (row.feature_link_broken_at ? '끊김' : row.feature_id ? '정상' : '없음'),
  },
];

const shareLinkColumns: AdminTableColumn<AdminTripShareLinkSummary>[] = [
  {
    key: 'share_id',
    header: 'share_id',
    cell: (row) => <span className="font-mono text-xs">{row.share_id}</span>,
  },
  {
    key: 'visibility',
    header: '권한',
    cell: (row) => row.visibility,
  },
  {
    key: 'expires_at',
    header: '만료',
    cell: (row) => formatDateTime(row.expires_at),
  },
  {
    key: 'revoked_at',
    header: '폐기',
    cell: (row) => formatDateTime(row.revoked_at),
  },
  {
    key: 'last_used_at',
    header: '마지막 사용',
    cell: (row) => formatDateTime(row.last_used_at),
  },
];

const attachmentColumns: AdminTableColumn<AttachmentLibraryItem>[] = [
  {
    key: 'file',
    header: '파일',
    cell: (row) => (
      <span>
        <span className="block font-semibold text-ink">{row.original_filename}</span>
        <span className="block text-xs text-muted">
          {row.content_type} · {formatBytes(row.byte_size)}
        </span>
      </span>
    ),
  },
  {
    key: 'scope',
    header: '대상',
    cell: (row) => (
      <span>
        <span className="block">{attachmentScopeLabel[row.target_scope]}</span>
        <span className="block text-xs text-muted">
          {row.trip_day_index ? `${row.trip_day_index}일차` : row.poi_label ?? '—'}
        </span>
      </span>
    ),
  },
  {
    key: 'uploaded_by',
    header: '업로더',
    cell: (row) => (
      <Link href={`/admin/users/${row.uploaded_by_user_id}`} className="text-primary underline">
        {row.uploaded_by_email_masked ?? row.uploaded_by_user_id}
      </Link>
    ),
  },
  {
    key: 'download',
    header: '',
    cell: (row) => (
      <button
        type="button"
        onClick={async () => {
          const res = await adminApi(apiClient).fileDownloadUrl(row.attachment_id);
          window.open(res.download_url, '_blank', 'noopener,noreferrer');
        }}
        aria-label="다운로드"
        className="rounded-sm p-2 text-muted hover:bg-surface-soft hover:text-ink"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
      </button>
    ),
  },
];

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

function AdminPoiMapPreview({ poi }: { poi: AdminTripPoiSummary }) {
  if (poi.lon == null || poi.lat == null) {
    return (
      <div
        className="flex h-64 items-center justify-center rounded-sm border border-hairline bg-surface-soft text-sm text-muted"
        data-testid="admin-trip-poi-map-empty"
      >
        좌표가 없는 POI입니다.
      </div>
    );
  }

  const center: [number, number] = [poi.lon, poi.lat];
  const title = poi.feature_label ?? poi.feature_id ?? 'POI';
  return (
    <div
      className="h-64 overflow-hidden rounded-sm border border-hairline"
      data-testid="admin-trip-poi-map"
    >
      <VWorldMap
        apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? ''}
        center={center}
        zoom={15}
        layerType="Base"
        navigation
        scale={false}
        geolocate={false}
        animateCameraChanges={false}
        fallback={(info) => <MapFallback info={info} />}
        loadingSkeleton={<MapLoadingSkeleton />}
        className="h-full min-h-64"
        unsupportedTileFallback={{ label: 'VWorld tile' }}
      >
        <MakiMarker
          lngLat={center}
          icon={poi.custom_marker_icon ?? 'marker'}
          color={paletteHex(poi.custom_marker_color)}
          title={title}
          selected
          ariaLabel={title}
        />
        <Popup lngLat={center} maxWidth="240px" closeButton={false}>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-ink">{title}</p>
            <p className="text-xs text-muted">
              {poi.lon.toFixed(5)}, {poi.lat.toFixed(5)}
            </p>
          </div>
        </Popup>
      </VWorldMap>
    </div>
  );
}

function AdminTripPoiDialog({
  poi,
  onClose,
}: {
  poi: AdminTripPoiSummary;
  onClose: () => void;
}) {
  const title = poi.feature_label ?? poi.feature_id ?? 'Feature 없는 POI';
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-trip-poi-dialog-title"
        className="max-h-[90vh] w-full max-w-5xl overflow-auto rounded-sm bg-white p-5 shadow-lg"
        data-testid="admin-trip-poi-dialog"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 id="admin-trip-poi-dialog-title" className="text-lg font-bold text-ink">
              {title}
            </h3>
            <p className="mt-1 font-mono text-xs text-muted">{poi.attachment_id}</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/admin/pois/${poi.attachment_id}`}
              className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm text-ink hover:bg-surface-soft"
              data-testid="admin-trip-poi-detail-link"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              POI 상세
            </Link>
            <button
              type="button"
              onClick={onClose}
              aria-label="닫기"
              className="flex h-10 w-10 items-center justify-center rounded-sm border border-hairline text-ink hover:bg-surface-soft"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-4">
            <AdminPoiMapPreview poi={poi} />
            <pre
              className="max-h-72 overflow-auto rounded-sm border border-hairline bg-surface-soft p-3 text-xs"
              data-testid="admin-trip-poi-snapshot"
            >
              {JSON.stringify(poi.feature_snapshot, null, 2)}
            </pre>
          </div>
          <dl className="grid content-start gap-3 text-sm">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">날짜</dt>
              <dd>{formatDayLabel(poi.day_index, poi.day_date, poi.day_title)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">주소</dt>
              <dd>{poi.address_label ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">feature_id</dt>
              <dd className="break-all font-mono text-xs">{poi.feature_id ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">추가자</dt>
              <dd>
                <Link href={`/admin/users/${poi.added_by_user_id}`} className="text-primary underline">
                  {poi.added_by_email_masked ?? poi.added_by_user_id}
                </Link>
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">도착 / 출발</dt>
              <dd>
                {formatDateTime(poi.planned_arrival_at)} / {formatDateTime(poi.planned_departure_at)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">예산 / 실사용</dt>
              <dd>
                {formatAmount(poi.budget_amount, poi.currency)} /{' '}
                {formatAmount(poi.actual_amount, poi.currency)}
              </dd>
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
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">메모</dt>
              <dd>{poi.user_note ?? '—'}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}

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
      {impact.warnings.length > 0 && (
        <div className="text-xs text-muted">
          {impact.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AdminTripDetailPage() {
  const router = useRouter();
  const params = useParams<{ trip_id: string }>();
  const tripId = params.trip_id;
  const [trip, setTrip] = useState<AdminTripDetail | null>(null);
  const [statusDraft, setStatusDraft] = useState<TripStatus>('draft');
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [acting, setActing] = useState(false);
  const [selectedPoi, setSelectedPoi] = useState<AdminTripPoiSummary | null>(null);
  const [showOperationDialog, setShowOperationDialog] = useState(false);
  const [operationMode, setOperationMode] = useState<TripOperationMode>('day_move');
  const [operationDayIndex, setOperationDayIndex] = useState(1);
  const [operationReason, setOperationReason] = useState('');
  const [operationError, setOperationError] = useState<string | null>(null);
  const [operationImpact, setOperationImpact] = useState<AdminOperationImpact | null>(null);
  const [operationResult, setOperationResult] = useState<AdminOperationResult | null>(null);
  const [targetTripQuery, setTargetTripQuery] = useState('');
  const [targetTrips, setTargetTrips] = useState<AdminTripSummary[]>([]);
  const [targetTripId, setTargetTripId] = useState('');
  const [targetDayIndex, setTargetDayIndex] = useState(1);
  const [targetOwnerUserId, setTargetOwnerUserId] = useState('');
  const [tripDeleteChildPolicy, setTripDeleteChildPolicy] = useState<'keep' | 'delete'>('keep');
  const [childMovePolicy, setChildMovePolicy] = useState<'move' | 'delete'>('move');
  const [includePois, setIncludePois] = useState(true);
  const [includeAttachments, setIncludeAttachments] = useState(true);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getTrip(tripId)
      .then((res) => {
        if (cancelled) return;
        setTrip(res);
        setStatusDraft(res.status);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/trips');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [router, tripId]);

  const nextAvailableDayIndex = useMemo(() => {
    if (!trip || trip.days.length === 0) return 1;
    return Math.max(...trip.days.map((day) => day.day_index)) + 1;
  }, [trip]);

  const refreshTrip = async () => {
    const updated = await adminApi(apiClient).getTrip(tripId);
    setTrip(updated);
    setStatusDraft(updated.status);
  };

  const openOperationDialog = (mode: TripOperationMode) => {
    const firstDayIndex = trip?.days[0]?.day_index ?? 1;
    setOperationMode(mode);
    setOperationDayIndex(firstDayIndex);
    setOperationReason('');
    setOperationError(null);
    setOperationResult(null);
    setOperationImpact(null);
    setTargetTripQuery('');
    setTargetTrips(trip ? [trip] : []);
    setTargetTripId(trip?.trip_id ?? '');
    setTargetDayIndex(nextAvailableDayIndex);
    setTargetOwnerUserId('');
    setTripDeleteChildPolicy('keep');
    setChildMovePolicy('move');
    setIncludePois(true);
    setIncludeAttachments(true);
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
    const request = operationMode.startsWith('day_')
      ? adminApi(apiClient).getDayOperationImpact(tripId, operationDayIndex)
      : adminApi(apiClient).getTripOperationImpact(tripId);
    request
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
  }, [operationDayIndex, operationMode, showOperationDialog, tripId]);

  const onStatusSave = async () => {
    if (!trip || reason.trim().length < 1) return;
    setActing(true);
    try {
      const updated = await adminApi(apiClient).updateTripStatus(trip.trip_id, {
        status: statusDraft,
        access_reason: reason.trim(),
      });
      setTrip(updated);
      setStatusDraft(updated.status);
      setShowStatusDialog(false);
      setReason('');
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '상태 변경 실패');
    } finally {
      setActing(false);
    }
  };

  const onOperationSave = async () => {
    if (!trip || operationReason.trim().length < 1) return;
    const access_reason = operationReason.trim();
    setActing(true);
    setOperationError(null);
    setOperationResult(null);
    try {
      let result: AdminOperationResult;
      if (operationMode === 'trip_copy') {
        result = await adminApi(apiClient).copyTrip(trip.trip_id, {
          title: `${trip.title} copy`,
          target_trip_id: targetTripId || null,
          date_shift_days: 0,
          scope: 'all',
          access_reason,
        });
      } else if (operationMode === 'trip_move') {
        result = await adminApi(apiClient).moveTrip(trip.trip_id, {
          owner_user_id: targetOwnerUserId,
          access_reason,
        });
      } else if (operationMode === 'trip_delete') {
        result = await adminApi(apiClient).deleteTrip(trip.trip_id, {
          child_policy: tripDeleteChildPolicy,
          access_reason,
        });
      } else if (operationMode === 'day_copy') {
        result = await adminApi(apiClient).copyTripDay(trip.trip_id, operationDayIndex, {
          target_trip_id: targetTripId,
          target_day_index: targetDayIndex,
          include_pois: includePois,
          include_attachments: includeAttachments,
          access_reason,
        });
      } else if (operationMode === 'day_move') {
        result = await adminApi(apiClient).moveTripDay(trip.trip_id, operationDayIndex, {
          target_trip_id: targetTripId,
          target_day_index: targetDayIndex,
          poi_policy: childMovePolicy,
          attachment_policy: childMovePolicy,
          comment_policy: childMovePolicy,
          access_reason,
        });
      } else {
        result = await adminApi(apiClient).deleteTripDay(trip.trip_id, operationDayIndex, {
          poi_policy: 'delete',
          attachment_policy: 'delete',
          comment_policy: 'delete',
          access_reason,
        });
      }
      setOperationResult(result);
      if (operationMode === 'trip_delete') {
        router.replace('/admin/trips');
        return;
      }
      await refreshTrip();
      setOperationReason('');
    } catch (err) {
      setOperationError(err instanceof ApiError ? err.message : '운영 작업 실패');
    } finally {
      setActing(false);
    }
  };

  if (error) {
    return (
      <AdminPage title="여행 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!trip) {
    return (
      <AdminPage title="여행 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  const period =
    trip.start_date === trip.end_date
      ? formatDate(trip.start_date)
      : `${formatDate(trip.start_date)} ~ ${formatDate(trip.end_date)}`;
  const operationNeedsTargetTrip = operationMode === 'day_copy' || operationMode === 'day_move';
  const operationNeedsTargetDay = operationNeedsTargetTrip;
  const operationNeedsOwner = operationMode === 'trip_move';
  const operationConfirmDisabled =
    acting ||
    operationReason.trim().length < 1 ||
    (operationNeedsTargetTrip && !targetTripId) ||
    (operationNeedsTargetDay && targetDayIndex < 1) ||
    (operationNeedsOwner && !targetOwnerUserId);

  return (
    <AdminPage
      title={trip.title}
      description={`trip_id ${trip.trip_id}`}
      actions={
        <Link href="/admin/trips" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-trip-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">소유자</dt>
            <dd>
              <Link href={`/admin/users/${trip.owner_user_id}`} className="text-primary underline">
                {trip.owner_email_masked}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">owner_user_id</dt>
            <dd className="font-mono text-xs">{trip.owner_user_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">상태</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <select
                value={statusDraft}
                onChange={(e) => setStatusDraft(e.target.value as TripStatus)}
                className="rounded-sm border border-hairline px-2 py-1 text-sm"
                data-testid="admin-trip-status-select"
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={statusDraft === trip.status}
                onClick={() => setShowStatusDialog(true)}
                className="rounded-sm border border-primary px-3 py-1 text-sm text-primary disabled:opacity-50"
                data-testid="admin-trip-status-save"
              >
                저장
              </button>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">공개</dt>
            <dd>{trip.visibility}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">지역</dt>
            <dd>{trip.region_hint ?? trip.primary_region_code ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">기간</dt>
            <dd>{period}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">구성</dt>
            <dd>
              days {trip.day_count} / POI {trip.poi_count} / companions {trip.companion_count} /
              shares {trip.share_link_count}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">version</dt>
            <dd>{trip.version}</dd>
          </div>
        </dl>
        {trip.description && <p className="mt-4 text-sm text-ink">{trip.description}</p>}
      </Section>

      <Section title="운영 작업">
        <div className="flex flex-wrap gap-2" data-testid="admin-trip-operations">
          <button
            type="button"
            onClick={() => openOperationDialog('trip_copy')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-trip-copy-open"
          >
            <Copy className="h-4 w-4" aria-hidden="true" />
            여행 복사
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('trip_move')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-trip-move-open"
          >
            <MoveRight className="h-4 w-4" aria-hidden="true" />
            소유자 이전
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('trip_delete')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-error-text px-3 text-sm text-error-text hover:bg-error-bg"
            data-testid="admin-trip-delete-open"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            여행 삭제
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('day_copy')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-day-copy-open"
          >
            <Copy className="h-4 w-4" aria-hidden="true" />
            날짜 복사
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('day_move')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm hover:bg-surface-soft"
            data-testid="admin-day-move-open"
          >
            <MoveRight className="h-4 w-4" aria-hidden="true" />
            날짜 이동
          </button>
          <button
            type="button"
            onClick={() => openOperationDialog('day_delete')}
            className="inline-flex h-10 items-center gap-2 rounded-sm border border-error-text px-3 text-sm text-error-text hover:bg-error-bg"
            data-testid="admin-day-delete-open"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            날짜 삭제
          </button>
        </div>
      </Section>

      <Section title="동반자">
        <div data-testid="admin-trip-companions">
          <AdminTable
            columns={companionColumns}
            rows={trip.companions}
            rowKey={(row) => row.companion_id}
            empty="항목이 없습니다."
          />
        </div>
      </Section>

      <Section title="상세 계획">
        <div className="space-y-4">
          <div data-testid="admin-trip-days">
            <AdminTable
              columns={dayColumns}
              rows={trip.days}
              rowKey={(row) => String(row.day_index)}
              empty="날짜가 없습니다."
              initialSort={{ columnKey: 'day_index', desc: false }}
            />
          </div>
          <div data-testid="admin-trip-pois">
            <AdminTable
              columns={poiColumns}
              rows={trip.pois}
              rowKey={(row) => row.attachment_id}
              empty="등록된 POI가 없습니다."
              onRowClick={(row) => setSelectedPoi(row)}
              rowTestId={(row) => `admin-trip-poi-row-${row.attachment_id}`}
              initialSort={{ columnKey: 'day', desc: false }}
            />
          </div>
        </div>
      </Section>

      <Section title="공유 링크">
        <div data-testid="admin-trip-share-links">
          <AdminTable
            columns={shareLinkColumns}
            rows={trip.share_links}
            rowKey={(row) => row.share_id}
            empty="항목이 없습니다."
          />
        </div>
      </Section>

      <Section title="파일">
        <div data-testid="admin-trip-files">
          <AdminTable
            columns={attachmentColumns}
            rows={trip.attachments}
            rowKey={(row) => row.attachment_id}
            empty="파일이 없습니다."
          />
        </div>
      </Section>

      <Section title="최근 Audit">
        <div data-testid="admin-trip-audit-list">
          <AdminTable
            columns={auditColumns}
            rows={trip.recent_audit}
            rowKey={(row) => String(row.log_id)}
            empty="기록이 없습니다."
          />
        </div>
      </Section>

      {showStatusDialog && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-4 rounded-sm bg-white p-6">
            <h3 className="text-lg font-bold text-ink">여행 상태 변경</h3>
            <p className="text-xs text-muted">
              {trip.status} → {statusDraft}
            </p>
            <FormTextArea
              id="admin-trip-action-reason"
              label="사유"
              hint="감사 로그에 기록됩니다."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              data-testid="admin-trip-action-reason"
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
                onClick={onStatusSave}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-trip-action-confirm"
              >
                {acting ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
      {showOperationDialog && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-trip-operation-title"
            className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-sm bg-white p-6 shadow-lg"
            data-testid="admin-trip-operation-dialog"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="admin-trip-operation-title" className="text-lg font-bold text-ink">
                  {TRIP_OPERATION_LABELS[operationMode]}
                </h3>
                <p className="mt-1 font-mono text-xs text-muted">{trip.trip_id}</p>
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
                    setOperationMode(e.target.value as TripOperationMode);
                    setOperationResult(null);
                    setOperationError(null);
                  }}
                  className="w-full rounded-sm border border-hairline px-3 py-2"
                  data-testid="admin-trip-operation-mode"
                >
                  {OPERATION_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>

              {operationMode.startsWith('day_') && (
                <label className="space-y-1 text-sm">
                  <span className="block text-xs uppercase tracking-wide text-muted">원본 날짜</span>
                  <select
                    value={operationDayIndex}
                    onChange={(e) => {
                      setOperationDayIndex(Number(e.target.value));
                      setOperationResult(null);
                    }}
                    className="w-full rounded-sm border border-hairline px-3 py-2"
                    data-testid="admin-trip-operation-source-day"
                  >
                    {trip.days.map((day) => (
                      <option key={day.day_index} value={day.day_index}>
                        {formatDayLabel(day.day_index, day.date, day.title)}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {(operationMode === 'trip_copy' || operationNeedsTargetTrip) && (
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
                        data-testid="admin-operation-target-search"
                      />
                    </span>
                  </label>
                  <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_8rem]">
                    <label className="space-y-1 text-sm">
                      <span className="block text-xs uppercase tracking-wide text-muted">
                        대상 여행
                      </span>
                      <select
                        value={targetTripId}
                        onChange={(e) => setTargetTripId(e.target.value)}
                        className="w-full rounded-sm border border-hairline px-3 py-2"
                        data-testid="admin-operation-target-trip"
                      >
                        {operationMode === 'trip_copy' && <option value="">새 여행 생성</option>}
                        {targetTrips.map((item) => (
                          <option key={item.trip_id} value={item.trip_id}>
                            {item.title} · {item.owner_email_masked}
                          </option>
                        ))}
                      </select>
                    </label>
                    {operationNeedsTargetDay && (
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
                          data-testid="admin-operation-target-day"
                        />
                      </label>
                    )}
                  </div>
                </div>
              )}

              {operationMode === 'trip_move' && (
                <label className="space-y-1 text-sm md:col-span-2">
                  <span className="block text-xs uppercase tracking-wide text-muted">
                    새 owner_user_id
                  </span>
                  <input
                    value={targetOwnerUserId}
                    onChange={(e) => setTargetOwnerUserId(e.target.value)}
                    className="w-full rounded-sm border border-hairline px-3 py-2 font-mono text-sm"
                    placeholder="UUID"
                    data-testid="admin-operation-owner-id"
                  />
                </label>
              )}

              {operationMode === 'trip_delete' && (
                <label className="space-y-1 text-sm">
                  <span className="block text-xs uppercase tracking-wide text-muted">하위 항목</span>
                  <select
                    value={tripDeleteChildPolicy}
                    onChange={(e) => setTripDeleteChildPolicy(e.target.value as 'keep' | 'delete')}
                    className="w-full rounded-sm border border-hairline px-3 py-2"
                    data-testid="admin-operation-child-policy"
                  >
                    <option value="keep">유지</option>
                    <option value="delete">함께 삭제</option>
                  </select>
                </label>
              )}

              {operationMode === 'day_move' && (
                <label className="space-y-1 text-sm">
                  <span className="block text-xs uppercase tracking-wide text-muted">
                    하위 POI/파일/댓글
                  </span>
                  <select
                    value={childMovePolicy}
                    onChange={(e) => setChildMovePolicy(e.target.value as 'move' | 'delete')}
                    className="w-full rounded-sm border border-hairline px-3 py-2"
                    data-testid="admin-operation-move-policy"
                  >
                    <option value="move">대상으로 이동</option>
                    <option value="delete">함께 삭제</option>
                  </select>
                </label>
              )}

              {operationMode === 'day_copy' && (
                <div className="grid gap-2 text-sm">
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={includePois}
                      onChange={(e) => setIncludePois(e.target.checked)}
                      data-testid="admin-operation-include-pois"
                    />
                    POI 포함
                  </label>
                  <label className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={includeAttachments}
                      onChange={(e) => setIncludeAttachments(e.target.checked)}
                      data-testid="admin-operation-include-attachments"
                    />
                    파일 포함
                  </label>
                </div>
              )}

              <div className="md:col-span-2">
                <FormTextArea
                  id="admin-trip-operation-reason"
                  label="사유"
                  hint="감사 로그에 기록됩니다."
                  value={operationReason}
                  onChange={(e) => setOperationReason(e.target.value)}
                  rows={3}
                  data-testid="admin-trip-operation-reason"
                />
              </div>
            </div>

            <div className="mt-4">
              <OperationImpactPanel impact={operationImpact} />
            </div>

            {operationError && (
              <p
                className="mt-4 rounded-sm bg-error-bg p-3 text-sm text-error-text"
                data-testid="admin-trip-operation-error"
              >
                {operationError}
              </p>
            )}
            {operationResult && (
              <p
                className="mt-4 rounded-sm bg-success-bg p-3 text-sm text-success-text"
                data-testid="admin-trip-operation-result"
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
                data-testid="admin-trip-operation-confirm"
              >
                {acting ? '처리 중...' : '실행'}
              </button>
            </div>
          </div>
        </div>
      )}
      {selectedPoi && (
        <AdminTripPoiDialog poi={selectedPoi} onClose={() => setSelectedPoi(null)} />
      )}
    </AdminPage>
  );
}
