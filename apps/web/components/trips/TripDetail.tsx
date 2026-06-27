'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowLeft, CalendarDays, Loader2, MapPin, Users, Wifi } from 'lucide-react';
import {
  ApiError,
  TripRealtimeClient,
  authApi,
  isVersionConflictError,
  poiApi,
  tripRealtimeInvalidationKeys,
  tripApi,
  type TripRealtimeCloseInfo,
  type TripRealtimeEvent,
  type TripRealtimeStatus,
} from '@pinvi/api-client';
import type {
  FeatureSummary,
  PoiUpdate,
  TripStatus,
  TripUpdate,
  TripView,
  TripViewPoi,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { appendRank, reorderMoves, tripDaysToMapPoints } from '@pinvi/domain';
import { MapSearchBox } from '@/components/map/MapSearchBox';
import { ConflictDialog, type ConflictField } from '@/components/trips/ConflictDialog';
import { TripActions } from '@/components/trips/TripActions';
import { TripEditDialog } from '@/components/trips/TripEditDialog';
import { TripAttachments } from '@/components/trips/TripAttachments';
import { TripComments } from '@/components/trips/TripComments';
import { TripCompanions } from '@/components/trips/TripCompanions';
import { TripDayControls } from '@/components/trips/TripDayControls';
import { TripDayOptimize } from '@/components/trips/TripDayOptimize';
import { TripMapView } from '@/components/trips/TripMapView';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripShareLinks } from '@/components/trips/TripShareLinks';
import { TripTelegramTargets } from '@/components/trips/TripTelegramTargets';
import { hasPatchFields, pickConflictPatch } from '@/lib/conflictResolution';

const STATUS_LABEL: Record<TripStatus, string> = {
  draft: '초안',
  planned: '예정',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? '';
const PINVI_API_URL = process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801';
const REALTIME_STATUS_LABEL: Record<TripRealtimeStatus, string> = {
  idle: '오프라인',
  connecting: '연결 중',
  open: '연결됨',
  closed: '오프라인',
  error: '오류',
  'refreshing-auth': '인증 갱신 중',
  reconnecting: '재연결 대기',
  'permission-denied': '권한 없음',
  'connection-limited': '연결 제한',
  'rate-limited': '속도 제한',
};

interface PresenceEntry {
  userId: string;
  viewingDay: number | null;
  isOnline: boolean;
}

type TripConflictFieldKey = Extract<keyof TripUpdate, string>;
type PoiConflictFieldKey = Extract<keyof PoiUpdate, string>;

type ConflictState =
  | {
      target: 'trip';
      version: number;
      patch: TripUpdate;
      fields: ConflictField[];
    }
  | {
      target: 'poi';
      poiId: string;
      title: string;
      version: number;
      patch: PoiUpdate;
      fields: ConflictField[];
    };

interface MutationOptions {
  onConflict?: (latest: TripView | null) => void;
}

function formatDate(value: string | null): string {
  if (!value) return '미정';
  return new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }).format(
    new Date(value)
  );
}

function realtimeStatusDetail(
  status: TripRealtimeStatus,
  closeInfo: TripRealtimeCloseInfo | null,
): string | null {
  if (status === 'refreshing-auth') return '세션을 갱신한 뒤 다시 연결합니다.';
  if (status === 'reconnecting' && closeInfo?.category === 'connection-limited') {
    return '동시 연결 한도에 도달해 잠시 후 자동으로 다시 시도합니다.';
  }
  if (status === 'reconnecting' && closeInfo?.category === 'rate-limited') {
    return '메시지 전송량이 많아 잠시 후 자동으로 다시 시도합니다.';
  }
  if (status === 'reconnecting') return '잠시 후 자동으로 다시 시도합니다.';
  if (status === 'permission-denied') return '여행 접근 권한이 변경되었습니다.';
  if (status === 'connection-limited') return '동시 연결 한도에 도달해 대기 중입니다.';
  if (status === 'rate-limited') return '메시지 전송량이 많아 대기 중입니다.';
  if (status === 'error') return '연결 상태를 확인하고 있습니다.';
  if (closeInfo?.category === 'bad-message') return '마지막 연결이 heartbeat 제한으로 종료되었습니다.';
  return null;
}

function displayConflictValue(value: unknown): string {
  if (value == null || value === '') return '비움';
  if (typeof value === 'boolean') return value ? '예' : '아니오';
  return String(value);
}

function hasOwnField<T extends object, K extends Extract<keyof T, string>>(
  target: T,
  key: K,
): boolean {
  return Object.prototype.hasOwnProperty.call(target, key);
}

const TRIP_CONFLICT_FIELDS: Array<{
  key: TripConflictFieldKey;
  label: string;
  serverValue: (trip: TripView['trip']) => unknown;
}> = [
  { key: 'title', label: '제목', serverValue: (trip) => trip.title },
  { key: 'region_hint', label: '지역', serverValue: (trip) => trip.region_hint },
  { key: 'start_date', label: '시작일', serverValue: (trip) => trip.start_date },
  { key: 'end_date', label: '종료일', serverValue: (trip) => trip.end_date },
  { key: 'visibility', label: '공개 범위', serverValue: (trip) => trip.visibility },
  { key: 'status', label: '상태', serverValue: (trip) => trip.status },
];

const POI_CONFLICT_FIELDS: Array<{
  key: PoiConflictFieldKey;
  label: string;
  serverValue: (poi: TripViewPoi) => unknown;
}> = [
  { key: 'custom_marker_color', label: '마커 색', serverValue: (poi) => poi.marker_color },
  { key: 'custom_marker_icon', label: '마커 아이콘', serverValue: (poi) => poi.marker_icon },
  { key: 'planned_arrival_at', label: '도착', serverValue: (poi) => poi.planned_arrival_at },
  { key: 'planned_departure_at', label: '출발', serverValue: (poi) => poi.planned_departure_at },
  { key: 'budget_amount', label: '예산', serverValue: (poi) => poi.budget_amount },
  { key: 'actual_amount', label: '실제 비용', serverValue: (poi) => poi.actual_amount },
  { key: 'currency', label: '통화', serverValue: (poi) => poi.currency },
  { key: 'user_note', label: '메모', serverValue: (poi) => poi.user_note },
  { key: 'user_url', label: '링크', serverValue: (poi) => poi.user_url },
];

function buildTripConflictFields(patch: TripUpdate, trip: TripView['trip']): ConflictField[] {
  return TRIP_CONFLICT_FIELDS.filter((field) => hasOwnField(patch, field.key)).map((field) => ({
    key: field.key,
    label: field.label,
    serverValue: displayConflictValue(field.serverValue(trip)),
    myValue: displayConflictValue(patch[field.key]),
  }));
}

function buildPoiConflictFields(patch: PoiUpdate, poi: TripViewPoi): ConflictField[] {
  return POI_CONFLICT_FIELDS.filter((field) => hasOwnField(patch, field.key)).map((field) => ({
    key: field.key,
    label: field.label,
    serverValue: displayConflictValue(field.serverValue(poi)),
    myValue: displayConflictValue(patch[field.key]),
  }));
}

function findPoi(view: TripView | null, poiId: string): TripViewPoi | null {
  return view?.days.flatMap((day) => day.pois).find((poi) => poi.poi_id === poiId) ?? null;
}

export interface TripDetailProps {
  tripId: string;
}

export function TripDetail({ tripId }: TripDetailProps) {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [realtimeStatus, setRealtimeStatus] = useState<TripRealtimeStatus>('idle');
  const [realtimeCloseInfo, setRealtimeCloseInfo] = useState<TripRealtimeCloseInfo | null>(null);
  const [presence, setPresence] = useState<Map<string, PresenceEntry>>(() => new Map());
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [savingPoiId, setSavingPoiId] = useState<string | null>(null);
  const [editingPoiId, setEditingPoiId] = useState<string | null>(null);
  const [tripEditOpen, setTripEditOpen] = useState(false);
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [busy, setBusy] = useState(false);
  const realtimeClientRef = useRef<TripRealtimeClient | null>(null);
  const realtimeReloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reloadInFlightRef = useRef<Promise<TripView | null> | null>(null);

  const reload = useCallback(async (): Promise<TripView | null> => {
    if (reloadInFlightRef.current) return reloadInFlightRef.current;

    const request = (async () => {
      try {
        const res = await tripApi(apiClient).get(tripId);
        setView(res);
        setError(null);
        return res;
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '여행을 불러오지 못했습니다.');
        return null;
      }
    })();

    const tracked = request.finally(() => {
      if (reloadInFlightRef.current === tracked) reloadInFlightRef.current = null;
    });
    reloadInFlightRef.current = tracked;
    return tracked;
  }, [tripId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void reload().then((res) => {
      if (cancelled) return;
      if (res) setSelectedDayIndex((current) => current ?? res.days[0]?.day_index ?? null);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const scheduleRealtimeReload = useCallback(() => {
    if (realtimeReloadTimerRef.current != null) return;
    realtimeReloadTimerRef.current = setTimeout(() => {
      realtimeReloadTimerRef.current = null;
      void reload();
    }, 250);
  }, [reload]);

  const handleRealtimeEvent = useCallback(
    (event: TripRealtimeEvent) => {
      if (event.type === 'presence.update') {
        const userId = typeof event.payload?.user_id === 'string' ? event.payload.user_id : null;
        if (!userId) return;
        const viewingDay =
          typeof event.payload?.viewing_day === 'number' ? event.payload.viewing_day : null;
        const isOnline = event.payload?.is_online === true;
        setPresence((current) => {
          const next = new Map(current);
          next.set(userId, { userId, viewingDay, isOnline });
          return next;
        });
        return;
      }

      const invalidationKeys = tripRealtimeInvalidationKeys(event, tripId);
      if (invalidationKeys.length === 0) return;
      scheduleRealtimeReload();
    },
    [scheduleRealtimeReload, tripId]
  );

  useEffect(() => {
    setPresence(new Map());
    const client = new TripRealtimeClient({
      apiBaseUrl: PINVI_API_URL,
      tripId,
      onEvent: handleRealtimeEvent,
      onStatus: (status) => {
        setRealtimeStatus(status);
        if (status === 'open') setRealtimeCloseInfo(null);
      },
      onClose: setRealtimeCloseInfo,
      onAuthRefresh: async () => {
        try {
          await authApi(apiClient).refresh();
          return true;
        } catch {
          return false;
        }
      },
      onError: () => undefined,
    });
    realtimeClientRef.current = client;
    client.connect();
    return () => {
      client.disconnect();
      realtimeClientRef.current = null;
      if (realtimeReloadTimerRef.current != null) {
        clearTimeout(realtimeReloadTimerRef.current);
        realtimeReloadTimerRef.current = null;
      }
    };
  }, [handleRealtimeEvent, tripId]);

  useEffect(() => {
    realtimeClientRef.current?.setViewingDay(selectedDayIndex);
  }, [selectedDayIndex]);

  const mapPoints = useMemo(() => (view ? tripDaysToMapPoints(view.days) : []), [view]);
  const poiDay = useMemo(() => {
    const map = new Map<string, number>();
    for (const point of mapPoints) map.set(point.poiId, point.dayIndex);
    return map;
  }, [mapPoints]);

  const selectedDay = view?.days.find((day) => day.day_index === selectedDayIndex) ?? null;
  const selectedPoi =
    selectedDay?.pois.find((poi) => poi.poi_id === selectedPoiId) ??
    view?.days.flatMap((day) => day.pois).find((poi) => poi.poi_id === selectedPoiId) ??
    null;
  const onlinePresence = Array.from(presence.values()).filter((entry) => entry.isOnline);
  const realtimeLabel = REALTIME_STATUS_LABEL[realtimeStatus];
  const realtimeDetail = realtimeStatusDetail(realtimeStatus, realtimeCloseInfo);
  const showRealtimeBackoffNotice =
    realtimeStatus === 'connection-limited' ||
    realtimeStatus === 'rate-limited' ||
    (realtimeStatus === 'reconnecting' &&
      (realtimeCloseInfo?.category === 'connection-limited' ||
        realtimeCloseInfo?.category === 'rate-limited'));

  const openTripConflict = (patch: TripUpdate, latest: TripView | null) => {
    const latestTrip = latest?.trip ?? view?.trip ?? null;
    if (!latestTrip) {
      setMutationError('최신 여행 정보를 불러오지 못했습니다.');
      return;
    }
    setMutationError(null);
    setTripEditOpen(true);
    setConflict({
      target: 'trip',
      version: latestTrip.version,
      patch,
      fields: buildTripConflictFields(patch, latestTrip),
    });
  };

  const openPoiConflict = (poiId: string, patch: PoiUpdate, latest: TripView | null) => {
    const latestPoi = findPoi(latest, poiId) ?? findPoi(view, poiId);
    if (!latestPoi) {
      setMutationError('최신 장소 정보를 불러오지 못했습니다.');
      return;
    }
    setMutationError(null);
    setEditingPoiId(poiId);
    setConflict({
      target: 'poi',
      poiId,
      title: latestPoi.title ?? latestPoi.feature_id ?? '장소',
      version: latestPoi.version,
      patch,
      fields: buildPoiConflictFields(patch, latestPoi),
    });
  };

  const handleSelectPoi = (poiId: string) => {
    setSelectedPoiId(poiId);
    const dayIndex = poiDay.get(poiId);
    if (dayIndex != null) setSelectedDayIndex(dayIndex);
  };

  // 지도 마커 우클릭 → 해당 POI 선택 + 편집기 열기.
  const handleMarkerContextMenu = (poiId: string) => {
    handleSelectPoi(poiId);
    setEditingPoiId(poiId);
  };

  const runMutation = useCallback(
    async (fn: () => Promise<unknown>, options: MutationOptions = {}): Promise<boolean> => {
      setMutationError(null);
      setBusy(true);
      try {
        await fn();
        await reload();
        return true;
      } catch (err) {
        if (isVersionConflictError(err) && options.onConflict) {
          const latest = await reload();
          options.onConflict(latest);
          return false;
        }
        setMutationError(err instanceof ApiError ? err.message : '변경에 실패했습니다.');
        await reload();
        return false;
      } finally {
        setBusy(false);
      }
    },
    [reload]
  );

  const handleAddFeature = (feature: FeatureSummary) => {
    if (selectedDay == null) return;
    const coord = feature.coord;
    if (!coord) return;
    const last = selectedDay.pois[selectedDay.pois.length - 1]?.sort_order ?? null;
    void runMutation(() =>
      poiApi(apiClient).create(tripId, {
        day_index: selectedDay.day_index,
        sort_order: appendRank(last),
        feature_id: feature.feature_id,
        feature_snapshot: {
          coord: { lon: coord.lon, lat: coord.lat },
          name: feature.name,
          // 구 snapshot 읽기(`feature_snapshot.title`) 호환을 위해 title 도 함께 보존.
          title: feature.name,
          kind: feature.kind,
          marker_color: feature.marker_color,
          marker_icon: feature.marker_icon,
          category: feature.category ?? null,
        },
        currency: 'KRW',
      })
    );
  };

  const handleReorder = (orderedPoiIds: string[]) => {
    if (selectedDay == null) return;
    const currentSortById = new Map(selectedDay.pois.map((p) => [p.poi_id, p.sort_order]));
    const moves = reorderMoves(orderedPoiIds, currentSortById);
    if (moves.length === 0) return;
    void runMutation(() => poiApi(apiClient).reorder(tripId, { moves }));
  };

  const handleEditPoi = (poi: { poi_id: string; version: number }, patch: PoiUpdate) => {
    setSavingPoiId(poi.poi_id);
    return runMutation(
      async () => {
        await poiApi(apiClient).update(tripId, poi.poi_id, poi.version, patch);
        setEditingPoiId(null);
      },
      { onConflict: (latest) => openPoiConflict(poi.poi_id, patch, latest) }
    ).finally(() => setSavingPoiId(null));
  };

  const handleDelete = (poiId: string) => {
    void runMutation(() => poiApi(apiClient).delete(tripId, poiId));
  };

  const handleAddDay = () => {
    const nextIndex = (view?.days.reduce((max, d) => Math.max(max, d.day_index), 0) ?? 0) + 1;
    void runMutation(async () => {
      await tripApi(apiClient).createDay(tripId, { day_index: nextIndex });
      setSelectedDayIndex(nextIndex);
    });
  };

  const handleRenameDay = (dayIndex: number, title: string) => {
    void runMutation(() =>
      tripApi(apiClient).updateDay(tripId, dayIndex, { title: title || null })
    );
  };

  const handleDeleteDay = (dayIndex: number) => {
    void runMutation(async () => {
      await tripApi(apiClient).deleteDay(tripId, dayIndex);
      setSelectedDayIndex(null);
    });
  };

  const handleEditTrip = (patch: TripUpdate) => {
    const version = view?.trip.version ?? 1;
    void runMutation(
      async () => {
        await tripApi(apiClient).update(tripId, version, patch);
        setTripEditOpen(false);
      },
      { onConflict: (latest) => openTripConflict(patch, latest) }
    );
  };

  const handleUseServerConflict = () => {
    const current = conflict;
    setConflict(null);
    setMutationError(null);
    if (current?.target === 'trip') setTripEditOpen(false);
    if (current?.target === 'poi') setEditingPoiId(null);
    void reload();
  };

  const handleKeepEditingConflict = () => {
    const current = conflict;
    setConflict(null);
    if (current?.target === 'trip') setTripEditOpen(true);
    if (current?.target === 'poi') setEditingPoiId(current.poiId);
  };

  const handleApplyConflict = (selectedKeys: string[]) => {
    const current = conflict;
    if (!current) return;

    void (async () => {
      setBusy(true);
      setMutationError(null);
      try {
        if (current.target === 'trip') {
          const patch = pickConflictPatch(
            current.patch,
            selectedKeys as TripConflictFieldKey[]
          ) as TripUpdate;
          if (!hasPatchFields(patch)) {
            handleUseServerConflict();
            return;
          }
          await tripApi(apiClient).update(tripId, current.version, patch);
          setConflict(null);
          setTripEditOpen(false);
          await reload();
          return;
        }

        const patch = pickConflictPatch(
          current.patch,
          selectedKeys as PoiConflictFieldKey[]
        ) as PoiUpdate;
        if (!hasPatchFields(patch)) {
          handleUseServerConflict();
          return;
        }
        await poiApi(apiClient).update(tripId, current.poiId, current.version, patch);
        setConflict(null);
        setEditingPoiId(null);
        await reload();
      } catch (err) {
        if (isVersionConflictError(err)) {
          const latest = await reload();
          if (current.target === 'trip') {
            openTripConflict(current.patch, latest);
          } else {
            openPoiConflict(current.poiId, current.patch, latest);
          }
          return;
        }
        setMutationError(err instanceof ApiError ? err.message : '충돌 해결에 실패했습니다.');
      } finally {
        setBusy(false);
      }
    })();
  };

  if (loading) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-sm border border-hairline bg-white text-sm text-muted">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        불러오는 중…
      </div>
    );
  }

  if (error || !view) {
    return (
      <div className="space-y-4">
        <Link href="/trips" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          여행 목록
        </Link>
        <p
          role="alert"
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="trip-detail-error"
        >
          {error ?? '여행을 찾을 수 없습니다.'}
        </p>
      </div>
    );
  }

  const { trip, companions } = view;

  return (
    <div className="space-y-5">
      <Link href="/trips" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        여행 목록
      </Link>

      <header className="space-y-3 border-b border-hairline pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold text-ink md:text-3xl">{trip.title}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="h-4 w-4" aria-hidden="true" />
                {formatDate(trip.start_date)} – {formatDate(trip.end_date)}
              </span>
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-4 w-4" aria-hidden="true" />
                {trip.region_hint ?? trip.primary_region_code ?? '지역 미정'}
              </span>
              <span className="inline-flex items-center gap-1">
                <Users className="h-4 w-4" aria-hidden="true" />
                동반 {companions.length}명
              </span>
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <span className="rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
                {STATUS_LABEL[trip.status]}
              </span>
              <button
                type="button"
                onClick={() => setTripEditOpen(true)}
                className="h-8 rounded-sm border border-hairline bg-white px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft"
              >
                편집
              </button>
            </div>
            <TripActions tripId={tripId} />
          </div>
        </div>
        {view.broken_feature_count > 0 && (
          <p className="inline-flex items-center gap-1.5 rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            링크가 끊긴 장소 {view.broken_feature_count}곳 — 라이브러리에서 삭제됨
          </p>
        )}
        <p
          className="inline-flex items-center gap-1.5 rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted"
          data-testid="trip-realtime-status"
        >
          <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
          실시간 {realtimeLabel} · 접속 {onlinePresence.length}명
          {realtimeDetail && <span> · {realtimeDetail}</span>}
          {onlinePresence.some((entry) => entry.viewingDay != null) && (
            <span>
              {' '}
              · 보는 일자{' '}
              {onlinePresence
                .map((entry) => entry.viewingDay)
                .filter((day): day is number => day != null)
                .join(', ')}
            </span>
          )}
        </p>
        {realtimeStatus === 'permission-denied' && (
          <p
            role="alert"
            className="inline-flex flex-wrap items-center gap-2 rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text"
            data-testid="trip-realtime-permission-lost"
          >
            여행 접근 권한이 사라져 실시간 연결을 종료했습니다.
            <Link href="/trips" className="font-semibold underline">
              여행 목록으로 이동
            </Link>
          </p>
        )}
        {showRealtimeBackoffNotice && (
          <p
            role="status"
            className="inline-flex items-center gap-1.5 rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted"
            data-testid="trip-realtime-backoff-notice"
          >
            실시간 연결을 잠시 늦춰 다시 시도합니다. 화면 데이터는 저장된 변경 기준으로 계속 불러옵니다.
          </p>
        )}
      </header>

      {view.days.length > 0 && (
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="일자 선택">
          {view.days.map((day) => {
            const active = day.day_index === selectedDayIndex;
            return (
              <button
                key={day.day_index}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSelectedDayIndex(day.day_index)}
                className={
                  active
                    ? 'h-9 rounded-sm bg-ink px-3 text-sm font-semibold text-white'
                    : 'h-9 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft'
                }
              >
                {day.title ?? `${day.day_index}일차`}
              </button>
            );
          })}
        </div>
      )}

      <TripDayControls
        selectedDay={selectedDay}
        onAdd={handleAddDay}
        onRename={handleRenameDay}
        onDelete={handleDeleteDay}
        busy={busy}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="min-h-[460px]" aria-label="여행 지도">
          <TripMapView
            apiKey={VWORLD_API_KEY}
            points={mapPoints}
            selectedPoiId={selectedPoiId}
            onSelectPoi={handleSelectPoi}
            onMarkerContextMenu={handleMarkerContextMenu}
            className="h-full"
          />
        </section>
        <aside className="space-y-3" aria-label="장소 목록">
          {selectedDay && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-ink">장소 추가</p>
              <MapSearchBox onSelect={handleAddFeature} />
            </div>
          )}
          {selectedDay && (
            <TripDayOptimize
              tripId={tripId}
              dayIndex={selectedDay.day_index}
              poiCount={selectedDay.pois.length}
              onApplied={reload}
            />
          )}
          {mutationError && (
            <p
              role="alert"
              className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text"
              data-testid="poi-mutation-error"
            >
              {mutationError}
            </p>
          )}
          <TripPoiList
            pois={selectedDay?.pois ?? []}
            selectedPoiId={selectedPoiId}
            onSelectPoi={handleSelectPoi}
            editable={!busy}
            onReorder={handleReorder}
            onEditPoi={handleEditPoi}
            onDelete={handleDelete}
            savingPoiId={savingPoiId}
            editingPoiId={editingPoiId}
            onEditToggle={setEditingPoiId}
          />
          {selectedDay && (
            <TripAttachments
              tripId={tripId}
              dayIndex={selectedDay.day_index}
              title={`${selectedDay.day_index}일차 파일`}
            />
          )}
          {selectedPoi && (
            <TripAttachments
              tripId={tripId}
              poiId={selectedPoi.poi_id}
              title={`${selectedPoi.title ?? '선택 장소'} 파일`}
            />
          )}
        </aside>
      </div>

      <TripCompanions tripId={tripId} companions={companions} onChanged={reload} />

      <div className="grid gap-4 lg:grid-cols-2">
        <TripAttachments tripId={tripId} />
        <TripShareLinks tripId={tripId} shareLinks={view.share_links} onChanged={reload} />
      </div>

      <TripTelegramTargets tripId={tripId} />

      <TripComments tripId={tripId} />

      {tripEditOpen && (
        <TripEditDialog
          trip={trip}
          saving={busy}
          error={mutationError}
          onSave={handleEditTrip}
          onClose={() => setTripEditOpen(false)}
        />
      )}

      {conflict && (
        <ConflictDialog
          key={`${conflict.target}-${conflict.target === 'poi' ? conflict.poiId : tripId}-${conflict.version}`}
          title={conflict.target === 'trip' ? '여행 정보 충돌' : `${conflict.title} 편집 충돌`}
          description="다른 변경이 먼저 저장되었습니다. 각 필드에서 서버 값 또는 내 값을 고른 뒤 저장할 수 있습니다."
          fields={conflict.fields}
          saving={busy}
          onApply={handleApplyConflict}
          onUseServer={handleUseServerConflict}
          onKeepEditing={handleKeepEditingConflict}
        />
      )}
    </div>
  );
}
