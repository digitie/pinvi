'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  Eye,
  Layers,
  Loader2,
  MapPin,
  MessageSquare,
  Paperclip,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Share2,
  Users,
  Wifi,
} from 'lucide-react';
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
  PlaceSearchResult,
  TripDayUpdate,
  PoiUpdate,
  TripStatus,
  TripUpdate,
  TripView,
  TripViewPoi,
} from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';
import { appendRank, paletteHex, reorderMoves, tripDaysToMapPoints } from '@pinvi/domain';
import { MapSearchBox } from '@/components/map/MapSearchBox';
import { ConflictDialog, type ConflictField } from '@/components/trips/ConflictDialog';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { TripDayHeader } from '@/components/trips/TripDayHeader';
import { TripActions } from '@/components/trips/TripActions';
import { TripEditDialog } from '@/components/trips/TripEditDialog';
import { TripAttachments } from '@/components/trips/TripAttachments';
import { TripComments } from '@/components/trips/TripComments';
import { TripCompanions } from '@/components/trips/TripCompanions';
import { TripDayControls } from '@/components/trips/TripDayControls';
import { TripDayOptimize } from '@/components/trips/TripDayOptimize';
import { TripMapView } from '@/components/trips/TripMapView';
import {
  TripManualPoiDialog,
  type ManualPoiCreateInput,
} from '@/components/trips/TripManualPoiDialog';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripShareLinks } from '@/components/trips/TripShareLinks';
import { TripTelegramTargets } from '@/components/trips/TripTelegramTargets';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';
import { hasPatchFields, pickConflictPatch, resolveConflictKeys } from '@/lib/conflictResolution';
import {
  formatTripDate,
  formatTripDateRange,
  holidaysByDate,
  holidayLabel,
} from '@/lib/tripDateLabels';

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

type TripDetailPanelTab = 'plan' | 'files' | 'share' | 'people' | 'comments';

interface MutationOptions {
  onConflict?: (latest: TripView | null) => void;
}

function tripDurationDays(startDate: string | null, endDate: string | null): number | null {
  if (!startDate || !endDate) return null;
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null;
  return Math.floor((end - start) / 86_400_000) + 1;
}

function addDays(dateValue: string, offsetDays: number): string {
  const next = new Date(`${dateValue}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + offsetDays);
  return next.toISOString().slice(0, 10);
}

function validDateValue(value: string | null): boolean {
  if (!value) return true;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

function nextAvailableDayIndex(view: TripView): number {
  const used = new Set(view.days.map((day) => day.day_index));
  const maxExisting = view.days.reduce((max, day) => Math.max(max, day.day_index), 0);
  const limit = tripDurationDays(view.trip.start_date, view.trip.end_date);
  const maxCandidate = limit ?? maxExisting + 1;
  for (let dayIndex = 1; dayIndex <= maxCandidate; dayIndex += 1) {
    if (!used.has(dayIndex)) return dayIndex;
  }
  return maxCandidate + 1;
}

function plannedDateForDay(view: TripView, dayIndex: number): string | null {
  if (!view.trip.start_date) return null;
  return addDays(view.trip.start_date, dayIndex - 1);
}

function dayUsingDate(view: TripView, date: string, excludeDayIndex: number): number | null {
  return (
    view.days.find((day) => day.day_index !== excludeDayIndex && day.date === date)?.day_index ??
    null
  );
}

function addDayValidation(view: TripView, nextDayIndex: number): string | null {
  const { start_date: startDate, end_date: endDate } = view.trip;

  if (!Number.isInteger(nextDayIndex) || nextDayIndex < 1) {
    return '추가할 일자 순서를 확인해주세요.';
  }
  if (!validDateValue(startDate) || !validDateValue(endDate)) {
    return '여행 기간을 먼저 확인해주세요.';
  }
  if (
    startDate &&
    endDate &&
    Date.parse(`${endDate}T00:00:00Z`) < Date.parse(`${startDate}T00:00:00Z`)
  ) {
    return '종료일이 시작일보다 빠릅니다. 여행 기간을 먼저 수정해주세요.';
  }

  const maxTripDayCount = tripDurationDays(startDate, endDate);
  if (maxTripDayCount != null && nextDayIndex > maxTripDayCount) {
    return `여행 기간은 최대 ${maxTripDayCount}일입니다. 기간을 먼저 늘려주세요.`;
  }

  const nextDate = plannedDateForDay(view, nextDayIndex);
  if (nextDate && endDate && nextDate > endDate) {
    return '추가할 일자가 여행 종료일을 넘어갑니다. 기간을 먼저 늘려주세요.';
  }
  if (view.days.some((day) => day.day_index === nextDayIndex)) {
    return '이미 같은 일자가 있습니다.';
  }
  if (nextDate) {
    const duplicateDayIndex = dayUsingDate(view, nextDate, nextDayIndex);
    if (duplicateDayIndex != null) {
      return `${duplicateDayIndex}일차에서 이미 쓰는 날짜입니다.`;
    }
  }

  return null;
}

function dayDateUpdateValidation(
  view: TripView,
  dayIndex: number,
  nextDate: string | null,
): string | null {
  const { start_date: startDate, end_date: endDate } = view.trip;
  if (nextDate && !validDateValue(nextDate)) {
    return '일자 날짜를 확인해주세요.';
  }
  if (!nextDate) {
    return startDate && endDate ? '여행 기간이 있는 경우 일자 날짜가 필요합니다.' : null;
  }
  if (startDate && nextDate < startDate) {
    return '여행 기간 밖의 날짜입니다. 기간을 먼저 늘려주세요.';
  }
  if (endDate && nextDate > endDate) {
    return '여행 기간 밖의 날짜입니다. 기간을 먼저 늘려주세요.';
  }
  const duplicateDayIndex = dayUsingDate(view, nextDate, dayIndex);
  if (duplicateDayIndex != null) {
    return `이미 ${duplicateDayIndex}일차에서 쓰는 날짜입니다.`;
  }
  return null;
}

function isKoreaCoord(coord: { lon: number; lat: number }): boolean {
  return coord.lon >= 124 && coord.lon <= 132 && coord.lat >= 33 && coord.lat <= 43;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function cleanString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function buildManualPoiSnapshot(input: ManualPoiCreateInput): Record<string, unknown> {
  const candidate = input.candidate;
  const snapshot: Record<string, unknown> = {
    coord: { lon: input.coord.lon, lat: input.coord.lat },
    name: input.title,
    title: input.title,
    kind: 'place',
    marker_color: 'P-08',
    marker_icon: 'marker',
    source: 'manual',
  };

  if (input.addressLabel) snapshot.address_label = input.addressLabel;
  if (candidate) {
    const address = candidate.address;
    if (isRecord(address) || typeof address === 'string') {
      snapshot.address = address;
    } else if (input.addressLabel) {
      snapshot.address = { label: input.addressLabel };
    }
    if (isRecord(candidate.region)) snapshot.region = candidate.region;

    const reverseGeocode: Record<string, unknown> = {};
    const source = cleanString(candidate.source);
    const distanceM = optionalNumber(candidate.distance_m);
    const confidence = optionalNumber(candidate.confidence);
    if (source) reverseGeocode.source = source;
    if (distanceM != null) reverseGeocode.distance_m = distanceM;
    if (confidence != null) reverseGeocode.confidence = confidence;
    if (Object.keys(reverseGeocode).length > 0) snapshot.reverse_geocode = reverseGeocode;
  } else if (input.addressLabel) {
    snapshot.address = { label: input.addressLabel };
  }

  return snapshot;
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
  if (closeInfo?.category === 'bad-message')
    return '마지막 연결이 heartbeat 제한으로 종료되었습니다.';
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
  const mobileWebLayout = useMobileWebLayout();
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [realtimeStatus, setRealtimeStatus] = useState<TripRealtimeStatus>('idle');
  const [realtimeCloseInfo, setRealtimeCloseInfo] = useState<TripRealtimeCloseInfo | null>(null);
  const [presence, setPresence] = useState<Map<string, PresenceEntry>>(() => new Map());
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  // ADR-055 F2: POI가 있는 일자 삭제는 확인 다이얼로그를 거친다(409 DAY_HAS_POIS → force 재요청).
  const [dayDeleteConfirm, setDayDeleteConfirm] = useState<{
    dayIndex: number;
    poiCount: number;
  } | null>(null);
  const [visibleDayIndexes, setVisibleDayIndexes] = useState<Set<number>>(() => new Set());
  const [activePanel, setActivePanel] = useState<TripDetailPanelTab>('plan');
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false);
  const [desktopPanelCollapsed, setDesktopPanelCollapsed] = useState(false);
  const [mutationError, setMutationError] = useState<string | null>(null);
  // 외부(kakao/naver) pick 추가 후 best-effort auto-request 안내(F4). 다음 변경 시 자동 소거.
  const [addNotice, setAddNotice] = useState<string | null>(null);
  const [savingPoiId, setSavingPoiId] = useState<string | null>(null);
  const [editingPoiId, setEditingPoiId] = useState<string | null>(null);
  const [manualPoiCoord, setManualPoiCoord] = useState<{ lon: number; lat: number } | null>(null);
  const [tripEditOpen, setTripEditOpen] = useState(false);
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [busy, setBusy] = useState(false);
  const realtimeClientRef = useRef<TripRealtimeClient | null>(null);
  const realtimeReloadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reloadInFlightRef = useRef<Promise<TripView | null> | null>(null);
  // Track the latest viewing day so a freshly (re)created realtime client can re-apply it
  // without adding selectedDayIndex to the client-creation effect deps (T-289).
  const selectedDayIndexRef = useRef(selectedDayIndex);
  selectedDayIndexRef.current = selectedDayIndex;

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
    [scheduleRealtimeReload, tripId],
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
    client.setViewingDay(selectedDayIndexRef.current);
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

  const dayIndexes = useMemo(() => view?.days.map((day) => day.day_index) ?? [], [view]);
  const dayIndexesKey = dayIndexes.join('|');

  useEffect(() => {
    setVisibleDayIndexes((current) => {
      if (dayIndexes.length === 0) return current.size === 0 ? current : new Set();

      const retained = dayIndexes.filter((dayIndex) => current.has(dayIndex));
      const nextIndexes = current.size === 0 || retained.length === 0 ? dayIndexes : retained;
      if (
        nextIndexes.length === current.size &&
        nextIndexes.every((dayIndex) => current.has(dayIndex))
      ) {
        return current;
      }
      return new Set(nextIndexes);
    });
  }, [dayIndexes, dayIndexesKey]);

  const allMapPoints = useMemo(() => (view ? tripDaysToMapPoints(view.days) : []), [view]);
  const mapPoints = useMemo(() => {
    if (visibleDayIndexes.size === 0) return allMapPoints;
    return allMapPoints.filter((point) => visibleDayIndexes.has(point.dayIndex));
  }, [allMapPoints, visibleDayIndexes]);
  const plannedFeatureIds = useMemo(() => {
    const ids = new Set<string>();
    for (const day of view?.days ?? []) {
      for (const poi of day.pois) {
        if (poi.feature_id) ids.add(poi.feature_id);
      }
    }
    return ids;
  }, [view]);
  const poiDay = useMemo(() => {
    const map = new Map<string, number>();
    for (const point of allMapPoints) map.set(point.poiId, point.dayIndex);
    return map;
  }, [allMapPoints]);

  const selectedDay = view?.days.find((day) => day.day_index === selectedDayIndex) ?? null;
  const selectedPoi =
    selectedDay?.pois.find((poi) => poi.poi_id === selectedPoiId) ??
    view?.days.flatMap((day) => day.pois).find((poi) => poi.poi_id === selectedPoiId) ??
    null;
  const onlinePresence = Array.from(presence.values()).filter((entry) => entry.isOnline);
  const holidayMap = useMemo(() => holidaysByDate(view?.days ?? []), [view?.days]);
  const realtimeLabel = REALTIME_STATUS_LABEL[realtimeStatus];
  const realtimeDetail = realtimeStatusDetail(realtimeStatus, realtimeCloseInfo);
  const nextDayIndex = view ? nextAvailableDayIndex(view) : 1;
  const nextDayDate = view ? plannedDateForDay(view, nextDayIndex) : null;
  const addDayDisabledReason = view ? addDayValidation(view, nextDayIndex) : null;
  const canAddDay = addDayDisabledReason == null;
  const addDayLabel = `${nextDayIndex}일차 추가`;
  const addDayTitle = addDayDisabledReason ?? addDayLabel;
  const visibleLayerCount =
    view?.days.filter((day) => visibleDayIndexes.size === 0 || visibleDayIndexes.has(day.day_index))
      .length ?? 0;
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
    setActivePanel('plan');
    setSelectedPoiId(poiId);
    const dayIndex = poiDay.get(poiId);
    if (dayIndex != null) {
      setSelectedDayIndex(dayIndex);
      setVisibleDayIndexes((current) => {
        if (current.size === 0 || current.has(dayIndex)) return current;
        const next = new Set(current);
        next.add(dayIndex);
        return next;
      });
    }
    if (mobileWebLayout) setMobilePanelOpen(false);
  };

  const handleSelectDay = (dayIndex: number) => {
    setActivePanel('plan');
    setSelectedDayIndex(dayIndex);
    setVisibleDayIndexes((current) => {
      if (current.size === 0 || current.has(dayIndex)) return current;
      const next = new Set(current);
      next.add(dayIndex);
      return next;
    });
  };

  const toggleDayVisibility = (dayIndex: number) => {
    const allVisible = visibleDayIndexes.size === 0;
    const currentVisible = allVisible
      ? dayIndexes
      : dayIndexes.filter((candidate) => visibleDayIndexes.has(candidate));
    const isVisible = allVisible || visibleDayIndexes.has(dayIndex);
    if (isVisible && currentVisible.length <= 1) return;

    const next = new Set(currentVisible);
    if (isVisible) {
      next.delete(dayIndex);
      if (selectedDayIndex === dayIndex) setSelectedDayIndex(next.values().next().value ?? null);
    } else {
      next.add(dayIndex);
    }
    setVisibleDayIndexes(next);
  };

  // 지도 마커 우클릭 → 해당 POI 선택 + 편집기 열기.
  const handleMarkerContextMenu = (poiId: string) => {
    handleSelectPoi(poiId);
    setEditingPoiId(poiId);
  };

  const runMutation = useCallback(
    async (fn: () => Promise<unknown>, options: MutationOptions = {}): Promise<boolean> => {
      setMutationError(null);
      setAddNotice(null);
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
    [reload],
  );

  // 공용 POI 생성 — feature marker(handleAddFeature)와 검색 결과(handleAddPlace)가 함께 쓴다.
  const addPoiToSelectedDay = (input: {
    feature_id: string | null;
    source: 'feature' | 'manual' | 'kakao' | 'naver';
    external_ref: { provider: 'kakao' | 'naver'; external_id: string; deep_link_url: string | null } | null;
    coord: { lon: number; lat: number };
    name: string;
    category: string | null;
    marker_color: string | null;
    marker_icon: string | null;
    kind?: string | null;
  }): Promise<boolean> => {
    if (selectedDay == null) return Promise.resolve(false);
    setAddNotice(null);
    const last = selectedDay.pois[selectedDay.pois.length - 1]?.sort_order ?? null;
    return runMutation(() =>
      poiApi(apiClient).create(tripId, {
        day_index: selectedDay.day_index,
        sort_order: appendRank(last),
        feature_id: input.feature_id,
        source: input.source,
        external_ref: input.external_ref,
        feature_snapshot: {
          coord: { lon: input.coord.lon, lat: input.coord.lat },
          name: input.name,
          // 구 snapshot 읽기(`feature_snapshot.title`) 호환을 위해 title 도 함께 보존.
          title: input.name,
          marker_color: input.marker_color,
          marker_icon: input.marker_icon,
          category: input.category,
          ...(input.kind != null ? { kind: input.kind } : {}),
        },
        currency: 'KRW',
      }),
    );
  };

  const guardDaySelected = (): boolean => {
    if (selectedDay != null) return true;
    setActivePanel('plan');
    setMutationError('일자를 먼저 선택해주세요.');
    if (mobileWebLayout) setMobilePanelOpen(true);
    return false;
  };

  // 지도 feature marker "추가" — feature_id 연결.
  const handleAddFeature = (feature: FeatureSummary) => {
    if (!guardDaySelected() || !feature.coord) return;
    void addPoiToSelectedDay({
      feature_id: feature.feature_id,
      source: 'feature',
      external_ref: null,
      coord: feature.coord,
      name: feature.name,
      category: feature.category ?? null,
      marker_color: feature.marker_color,
      marker_icon: feature.marker_icon,
      kind: feature.kind,
    });
  };

  // 검색 결과 pick(F3/F4) — 외부(kakao/naver)는 source + external_ref만 저장 → 서버가 feature-request를
  // best-effort auto-fire. feature는 feature_id 연결, address/my_poi는 manual snapshot.
  const handleAddPlace = (result: PlaceSearchResult) => {
    if (!guardDaySelected()) return;
    if (!result.coord) {
      setMutationError('좌표가 없는 항목은 지도에 추가할 수 없습니다.');
      return;
    }
    // external_ref는 external_id가 있을 때만 만든다. external_id 없는 kakao/naver 행은
    // auto-fire할 참조가 없으므로 manual snapshot으로 저장한다(source=kakao+ref=null 금지 —
    // 서버 auto-request 계약 준수).
    const provider = result.source === 'kakao' || result.source === 'naver' ? result.source : null;
    const externalRef =
      provider && result.external_id
        ? {
            provider,
            external_id: result.external_id,
            deep_link_url: result.provider_url ?? null,
          }
        : null;
    // §5.1(ADR-054): kakao/naver 파생 콘텐츠(category/마커 스타일 등)는 DB에 저장 금지.
    // provider 소스면 name + coord + external_ref만 남기고 provider 파생 필드는 null로 보낸다
    // (external_id가 없어 manual로 저장되는 provider 행도 동일하게 콘텐츠 미저장).
    const providerSourced = provider != null;
    void addPoiToSelectedDay({
      feature_id: result.feature_id,
      source: externalRef ? externalRef.provider : result.feature_id ? 'feature' : 'manual',
      external_ref: externalRef,
      coord: result.coord,
      name: result.name,
      category: providerSourced ? null : (result.category ?? null),
      marker_color: providerSourced ? null : (result.marker_color ?? null),
      marker_icon: providerSourced ? null : (result.marker_icon ?? null),
    }).then((ok) => {
      // external_ref로 저장된 경우에만 서버가 상세 정보를 best-effort로 요청한다.
      if (ok && externalRef) {
        const label = externalRef.provider === 'kakao' ? '카카오' : '네이버';
        setAddNotice(`${label} 장소를 추가했어요. 상세 정보는 준비되는 대로 표시됩니다.`);
      }
    });
  };

  const handleCreatePoiAtCoordinate = (coord: { lon: number; lat: number }) => {
    if (selectedDay == null) {
      setActivePanel('plan');
      setMutationError('일자를 먼저 선택해주세요.');
      if (mobileWebLayout) setMobilePanelOpen(true);
      return;
    }
    if (!isKoreaCoord(coord)) {
      setMutationError('대한민국 범위 좌표만 추가할 수 있습니다.');
      return;
    }
    setMutationError(null);
    setManualPoiCoord({
      lon: Number(coord.lon.toFixed(6)),
      lat: Number(coord.lat.toFixed(6)),
    });
  };

  const handleCreateManualPoi = (input: ManualPoiCreateInput): Promise<boolean> => {
    if (selectedDay == null) {
      setMutationError('일자를 먼저 선택해주세요.');
      return Promise.resolve(false);
    }
    const last = selectedDay.pois[selectedDay.pois.length - 1]?.sort_order ?? null;
    return runMutation(async () => {
      const created = await poiApi(apiClient).create(tripId, {
        day_index: selectedDay.day_index,
        sort_order: appendRank(last),
        feature_id: null,
        feature_snapshot: buildManualPoiSnapshot(input),
        custom_marker_color: 'P-08',
        custom_marker_icon: 'marker',
        currency: 'KRW',
      });
      setSelectedDayIndex(selectedDay.day_index);
      setSelectedPoiId(created.attachment_id);
    }).then((ok) => {
      if (ok) setManualPoiCoord(null);
      return ok;
    });
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
      { onConflict: (latest) => openPoiConflict(poi.poi_id, patch, latest) },
    ).finally(() => setSavingPoiId(null));
  };

  const handleDelete = (poiId: string) => {
    void runMutation(() => poiApi(apiClient).delete(tripId, poiId));
  };

  const handleAddDay = () => {
    if (!view) {
      setMutationError('여행 정보를 불러온 뒤 일자를 추가할 수 있습니다.');
      return;
    }
    const validationMessage = addDayValidation(view, nextDayIndex);
    if (validationMessage) {
      setMutationError(validationMessage);
      return;
    }
    void runMutation(async () => {
      await tripApi(apiClient).createDay(tripId, { day_index: nextDayIndex, date: nextDayDate });
      setSelectedDayIndex(nextDayIndex);
      setVisibleDayIndexes((current) => {
        const next = new Set(current.size === 0 ? dayIndexes : Array.from(current));
        next.add(nextDayIndex);
        return next;
      });
    });
  };

  const dayConflictNotice = () =>
    setMutationError('다른 사용자가 이 일자를 먼저 변경했습니다. 최신 내용으로 다시 불러왔어요.');

  const handleUpdateDay = (
    dayIndex: number,
    next: { title: string; date: string | null; marker_color: string | null },
  ) => {
    if (!view) return;
    const day = view.days.find((d) => d.day_index === dayIndex);
    if (!day) return;
    const validationMessage = dayDateUpdateValidation(view, dayIndex, next.date);
    if (validationMessage) {
      setMutationError(validationMessage);
      return;
    }
    const patch: TripDayUpdate = {};
    const nextTitle = next.title || null;
    if (nextTitle !== day.title) patch.title = nextTitle;
    if (next.date !== day.date) patch.date = next.date;
    // ADR-055 F6: 일자 색 override(팔레트 키 또는 null=기본색).
    if (next.marker_color !== (day.marker_color ?? null)) patch.marker_color = next.marker_color;
    if (!hasPatchFields(patch)) return;
    void runMutation(
      () => tripApi(apiClient).updateDay(tripId, dayIndex, day.version, patch),
      { onConflict: dayConflictNotice },
    );
  };

  const dayVersion = (dayIndex: number) =>
    view?.days.find((d) => d.day_index === dayIndex)?.version ?? 0;

  const deleteDayRequest = (dayIndex: number, force: boolean) =>
    runMutation(
      async () => {
        await tripApi(apiClient).deleteDay(tripId, dayIndex, dayVersion(dayIndex), { force });
        setSelectedDayIndex(null);
      },
      { onConflict: dayConflictNotice },
    );

  const handleDeleteDay = (dayIndex: number) => {
    // POI가 없으면 바로 삭제. 있으면(409 DAY_HAS_POIS) 확인 다이얼로그를 띄운다(F2).
    void (async () => {
      setMutationError(null);
      setBusy(true);
      try {
        await tripApi(apiClient).deleteDay(tripId, dayIndex, dayVersion(dayIndex));
        setSelectedDayIndex(null);
        await reload();
      } catch (err) {
        if (err instanceof ApiError && err.status === 409 && err.code === 'DAY_HAS_POIS') {
          const poiCount =
            typeof err.details?.poi_count === 'number' ? err.details.poi_count : 0;
          setDayDeleteConfirm({ dayIndex, poiCount });
          return;
        }
        if (isVersionConflictError(err)) {
          await reload();
          dayConflictNotice();
          return;
        }
        setMutationError(err instanceof ApiError ? err.message : '변경에 실패했습니다.');
        await reload();
      } finally {
        setBusy(false);
      }
    })();
  };

  const confirmForceDeleteDay = () => {
    const target = dayDeleteConfirm;
    if (!target) return;
    setDayDeleteConfirm(null);
    void deleteDayRequest(target.dayIndex, true);
  };

  const handleEditTrip = (patch: TripUpdate) => {
    const version = view?.trip.version ?? 1;
    void runMutation(
      async () => {
        await tripApi(apiClient).update(tripId, version, patch);
        setTripEditOpen(false);
      },
      { onConflict: (latest) => openTripConflict(patch, latest) },
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

    // Carry through any patch field not represented in the dialog so a hardcoded
    // conflict-field-list drift cannot silently drop the user's edit (T-290).
    const effectiveKeys = resolveConflictKeys(
      Object.keys(current.patch),
      current.fields.map((field) => field.key),
      selectedKeys,
    );

    void (async () => {
      setBusy(true);
      setMutationError(null);
      try {
        if (current.target === 'trip') {
          const patch = pickConflictPatch(
            current.patch,
            effectiveKeys as TripConflictFieldKey[],
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
          effectiveKeys as PoiConflictFieldKey[],
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
        <Link
          href="/trips"
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"
        >
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
  const totalPoiCount = view.days.reduce((count, day) => count + day.pois.length, 0);
  const selectedDayLabel = selectedDay?.title ?? `${selectedDay?.day_index ?? ''}일차`;
  const panelTabs: Array<{
    id: TripDetailPanelTab;
    label: string;
    count?: number;
    icon: typeof Layers;
  }> = [
    { id: 'plan', label: '일정', count: view.days.length, icon: Layers },
    { id: 'files', label: '파일', icon: Paperclip },
    { id: 'share', label: '공유', icon: Share2 },
    { id: 'people', label: '동행', count: companions.length, icon: Users },
    { id: 'comments', label: '댓글', icon: MessageSquare },
  ];
  const renderPanelTabs = () =>
    panelTabs.map((tab) => {
      const Icon = tab.icon;
      const active = tab.id === activePanel;
      return (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active}
          aria-controls={`trip-panel-${tab.id}`}
          onClick={() => setActivePanel(tab.id)}
          className={
            active
              ? 'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-sm bg-ink px-3 text-sm font-semibold text-white'
              : 'inline-flex h-9 shrink-0 items-center gap-1.5 rounded-sm px-3 text-sm font-semibold text-muted hover:bg-surface-soft hover:text-ink'
          }
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
          {tab.label}
          {tab.count != null && (
            <span
              className={
                active
                  ? 'rounded-sm bg-white/20 px-1.5 text-xs text-white'
                  : 'rounded-sm bg-surface-soft px-1.5 text-xs text-muted'
              }
            >
              {tab.count}
            </span>
          )}
        </button>
      );
    });
  const detailGridClassName = mobileWebLayout
    ? 'relative flex min-h-0 flex-1 flex-col'
    : desktopPanelCollapsed
      ? 'relative flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[minmax(0,1fr)]'
      : 'relative flex min-h-0 flex-1 flex-col lg:grid lg:grid-cols-[420px_minmax(0,1fr)] xl:grid-cols-[460px_minmax(0,1fr)]';
  const detailPanelClassName = mobileWebLayout
    ? `${
        mobilePanelOpen ? 'flex' : 'hidden'
      } absolute inset-y-0 left-0 z-30 w-[min(86vw,360px)] max-w-[calc(100%-2.5rem)] min-h-0 flex-col border-r border-hairline bg-white shadow-card`
    : `${
        mobilePanelOpen ? 'flex' : 'hidden'
      } absolute inset-y-0 left-0 z-30 w-[min(82vw,360px)] max-w-[calc(100%-3rem)] min-h-0 flex-col border-r border-hairline bg-white shadow-card lg:static lg:h-full lg:w-auto lg:max-w-none lg:shadow-none ${
        desktopPanelCollapsed ? 'lg:hidden' : 'lg:flex'
      }`;

  return (
    <div
      className={
        mobileWebLayout
          ? 'relative flex h-[100svh] min-h-[100svh] flex-col overflow-hidden bg-canvas'
          : '-mx-4 -my-6 flex min-h-[calc(100vh-4rem)] flex-col bg-surface-soft md:-mx-6 md:-my-8'
      }
      data-testid="trip-detail-shell"
    >
      {mobileWebLayout ? (
        <header
          className="pointer-events-none absolute left-2 right-2 top-2 z-40 space-y-2"
          aria-label="여행 작업 패널"
          data-testid="trip-top-panel"
        >
          <div className="pointer-events-auto flex h-12 items-center gap-1.5 rounded-sm border border-hairline bg-white/95 p-1.5 shadow-card backdrop-blur">
            <Link
              href="/trips"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink"
              aria-label="여행 목록"
              title="여행 목록"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            </Link>
            <div className="min-w-0 flex-1 px-1">
              <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
                <h1 className="truncate text-sm font-bold text-ink">{trip.title}</h1>
                <span className="hidden shrink-0 rounded-sm bg-surface-soft px-1.5 py-0.5 text-[11px] font-semibold text-muted min-[390px]:inline">
                  {STATUS_LABEL[trip.status]}
                </span>
              </div>
              <p className="mt-0.5 flex min-w-0 items-center gap-2 text-[11px] text-muted">
                <span className="shrink-0">
                  {view.days.length}일 · {totalPoiCount}곳
                </span>
                <span className="truncate">
                  {trip.region_hint ?? trip.primary_region_code ?? '지역 미정'}
                </span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => setMobilePanelOpen((open) => !open)}
              aria-controls="trip-detail-panel"
              aria-expanded={mobilePanelOpen}
              aria-label={mobilePanelOpen ? '패널 닫기' : '패널 열기'}
              title={mobilePanelOpen ? '패널 닫기' : '패널 열기'}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm text-ink hover:bg-surface-soft"
            >
              {mobilePanelOpen ? (
                <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
              ) : (
                <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
            <button
              type="button"
              onClick={handleAddDay}
              disabled={!canAddDay || busy}
              title={addDayTitle}
              aria-label={addDayLabel}
              aria-describedby={addDayDisabledReason ? 'trip-layer-add-disabled-reason' : undefined}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-ink text-white hover:bg-ink/90 disabled:opacity-50"
              data-testid="trip-add-layer"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          {realtimeStatus === 'permission-denied' && (
            <p
              role="alert"
              className="pointer-events-auto inline-flex flex-wrap items-center gap-2 rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text"
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
              className="pointer-events-auto inline-flex items-center gap-1.5 rounded-sm bg-white/95 px-3 py-2 text-xs text-muted shadow-card"
              data-testid="trip-realtime-backoff-notice"
            >
              실시간 연결을 잠시 늦춰 다시 시도합니다.
            </p>
          )}
          {addDayDisabledReason && (
            <span id="trip-layer-add-disabled-reason" className="sr-only">
              {addDayDisabledReason}
            </span>
          )}
        </header>
      ) : (
        <header
          className="z-20 border-b border-hairline bg-white"
          aria-label="여행 작업 패널"
          data-testid="trip-top-panel"
        >
          <div className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-5">
            <div className="flex min-w-0 items-start gap-3">
              <Link
                href="/trips"
                className="mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-hairline text-muted hover:bg-surface-soft hover:text-ink"
                aria-label="여행 목록"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              </Link>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="truncate text-lg font-bold text-ink md:text-xl">{trip.title}</h1>
                  <span className="shrink-0 rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
                    {STATUS_LABEL[trip.status]}
                  </span>
                </div>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted md:text-sm">
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays className="h-4 w-4" aria-hidden="true" />
                    {formatTripDateRange(trip.start_date, trip.end_date, holidayMap)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <MapPin className="h-4 w-4" aria-hidden="true" />
                    {trip.region_hint ?? trip.primary_region_code ?? '지역 미정'}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Layers className="h-4 w-4" aria-hidden="true" />
                    {view.days.length}일 · {totalPoiCount}개 장소
                  </span>
                  <span>업데이트 {formatTripDate(trip.updated_at)}</span>
                </p>
              </div>
            </div>

            <div className="flex max-w-full flex-nowrap items-center gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible md:pb-0 [&>*]:shrink-0">
              <button
                type="button"
                onClick={() => setDesktopPanelCollapsed((collapsed) => !collapsed)}
                aria-controls="trip-detail-panel"
                aria-expanded={!desktopPanelCollapsed}
                className="hidden h-9 items-center gap-1.5 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft lg:inline-flex"
              >
                {desktopPanelCollapsed ? (
                  <PanelLeftOpen className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
                )}
                {desktopPanelCollapsed ? '패널 열기' : '패널 접기'}
              </button>
              <button
                type="button"
                onClick={handleAddDay}
                disabled={!canAddDay || busy}
                title={addDayTitle}
                aria-describedby={
                  addDayDisabledReason ? 'trip-layer-add-disabled-reason' : undefined
                }
                className="inline-flex h-9 items-center gap-1.5 rounded-sm bg-ink px-3 text-sm font-semibold text-white hover:bg-ink/90 disabled:opacity-50"
                data-testid="trip-add-layer"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                {addDayLabel}
              </button>
              <button
                type="button"
                onClick={() => setActivePanel('share')}
                className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                <Share2 className="h-4 w-4" aria-hidden="true" />
                공유
              </button>
              <a
                href="#trip-map-canvas"
                className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                <Eye className="h-4 w-4" aria-hidden="true" />
                미리보기
              </a>
              <button
                type="button"
                onClick={() => setTripEditOpen(true)}
                className="h-9 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
              >
                편집
              </button>
              <TripActions tripId={tripId} />
            </div>
          </div>

          <div className="flex flex-col gap-2 border-t border-hairline px-4 py-2 md:flex-row md:items-center md:justify-between md:px-5">
            <div className="flex gap-1 overflow-x-auto" role="tablist" aria-label="여행 작업 탭">
              {renderPanelTabs()}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {addDayDisabledReason && (
                <p id="trip-layer-add-disabled-reason" className="text-xs text-muted">
                  {addDayDisabledReason}
                </p>
              )}
              {view.broken_feature_count > 0 && (
                <p className="inline-flex items-center gap-1.5 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  끊긴 장소 {view.broken_feature_count}곳
                </p>
              )}
              <p
                className="inline-flex flex-wrap items-center gap-1.5 rounded-sm bg-surface-soft px-2 py-1 text-xs text-muted"
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
              {(realtimeStatus === 'closed' || realtimeStatus === 'error') && (
                <button
                  type="button"
                  onClick={() => realtimeClientRef.current?.reconnect()}
                  className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-hairline px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft"
                  data-testid="trip-realtime-reconnect"
                >
                  <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
                  다시 연결
                </button>
              )}
            </div>
          </div>

          {realtimeStatus === 'permission-denied' && (
            <p
              role="alert"
              className="mx-4 mb-2 inline-flex flex-wrap items-center gap-2 rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text md:mx-5"
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
              className="mx-4 mb-2 inline-flex items-center gap-1.5 rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted md:mx-5"
              data-testid="trip-realtime-backoff-notice"
            >
              실시간 연결을 잠시 늦춰 다시 시도합니다. 화면 데이터는 저장된 변경 기준으로 계속
              불러옵니다.
            </p>
          )}
        </header>
      )}

      <div className={detailGridClassName}>
        <aside
          id="trip-detail-panel"
          className={detailPanelClassName}
          aria-label="여행 상세"
          data-testid="trip-detail-panel"
        >
          {mobileWebLayout && (
            <div className="shrink-0 border-b border-hairline bg-white p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-bold text-ink">{trip.title}</p>
                  <p className="mt-1 text-xs text-muted">
                    {formatTripDateRange(trip.start_date, trip.end_date, holidayMap)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setMobilePanelOpen(false)}
                  aria-label="패널 닫기"
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink"
                >
                  <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setTripEditOpen(true)}
                  className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline bg-white px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft"
                >
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                  편집
                </button>
                <button
                  type="button"
                  onClick={handleAddDay}
                  disabled={!canAddDay || busy}
                  title={addDayTitle}
                  aria-label={addDayLabel}
                  aria-describedby={
                    addDayDisabledReason ? 'trip-drawer-add-disabled-reason' : undefined
                  }
                  className="inline-flex h-8 items-center gap-1 rounded-sm bg-ink px-2.5 text-xs font-semibold text-white hover:bg-ink/90 disabled:opacity-50"
                  data-testid="trip-add-day-drawer"
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  {addDayLabel}
                </button>
                <TripActions tripId={tripId} />
              </div>
              {addDayDisabledReason && (
                <p id="trip-drawer-add-disabled-reason" className="mt-2 text-xs text-muted">
                  {addDayDisabledReason}
                </p>
              )}
              <div
                className="mt-3 flex gap-1 overflow-x-auto"
                role="tablist"
                aria-label="여행 작업 탭"
              >
                {renderPanelTabs()}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {view.broken_feature_count > 0 && (
                  <p className="inline-flex items-center gap-1.5 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">
                    <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                    끊긴 장소 {view.broken_feature_count}곳
                  </p>
                )}
                <p
                  className="inline-flex flex-wrap items-center gap-1.5 rounded-sm bg-surface-soft px-2 py-1 text-xs text-muted"
                  data-testid="trip-realtime-status"
                >
                  <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
                  실시간 {realtimeLabel} · 접속 {onlinePresence.length}명
                  {realtimeDetail && <span> · {realtimeDetail}</span>}
                </p>
                {(realtimeStatus === 'closed' || realtimeStatus === 'error') && (
                  <button
                    type="button"
                    onClick={() => realtimeClientRef.current?.reconnect()}
                    className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-hairline px-2.5 text-xs font-semibold text-ink hover:bg-surface-soft"
                    data-testid="trip-realtime-reconnect"
                  >
                    <Wifi className="h-3.5 w-3.5" aria-hidden="true" />
                    다시 연결
                  </button>
                )}
              </div>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            {activePanel === 'plan' && (
              <div
                id="trip-panel-plan"
                role="tabpanel"
                aria-label="일정"
                className={mobileWebLayout ? 'space-y-3 p-3' : 'space-y-4 p-4 md:p-5'}
              >
                <section className="space-y-3">
                  {!mobileWebLayout && (
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleAddDay}
                        disabled={!canAddDay || busy}
                        title={addDayTitle}
                        aria-describedby={
                          addDayDisabledReason ? 'trip-plan-add-disabled-reason' : undefined
                        }
                        className="inline-flex h-8 shrink-0 items-center gap-1 rounded-sm bg-ink px-2.5 text-xs font-semibold text-white hover:bg-ink/90 disabled:opacity-50"
                        data-testid="trip-add-day-inline"
                      >
                        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                        {addDayLabel}
                      </button>
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded-sm bg-surface-soft px-2 py-1 font-semibold text-muted">
                      {visibleLayerCount}/{view.days.length} 표시
                    </span>
                    <span className="rounded-sm bg-surface-soft px-2 py-1 text-muted">
                      일자 {view.days.length}
                    </span>
                    <span className="rounded-sm bg-surface-soft px-2 py-1 text-muted">
                      장소 {totalPoiCount}
                    </span>
                    <span className="min-w-0 rounded-sm bg-surface-soft px-2 py-1 text-muted">
                      선택 {selectedDay ? selectedDayLabel : '없음'}
                    </span>
                  </div>
                  {!mobileWebLayout && addDayDisabledReason && (
                    <p id="trip-plan-add-disabled-reason" className="text-xs text-muted">
                      {addDayDisabledReason}
                    </p>
                  )}
                </section>

                <section className="space-y-3" aria-label="일자 목록" data-testid="trip-layer-list">
                  {view.days.length > 0 && (
                    <div className="space-y-2" role="tablist" aria-label="일자 목록">
                      {view.days.map((day) => {
                        const active = day.day_index === selectedDayIndex;
                        const visible =
                          visibleDayIndexes.size === 0 || visibleDayIndexes.has(day.day_index);
                        const dayLabel = day.title ?? `${day.day_index}일차`;
                        const dayHolidayLabel = holidayLabel(day.holidays);
                        return (
                          <article
                            key={day.day_index}
                            className={
                              active
                                ? 'rounded-sm bg-white shadow-card ring-1 ring-primary/35'
                                : 'rounded-sm bg-white'
                            }
                          >
                            <div className="flex items-start gap-3 p-3">
                              <input
                                type="checkbox"
                                checked={visible}
                                onChange={() => toggleDayVisibility(day.day_index)}
                                disabled={visible && visibleLayerCount <= 1}
                                aria-label={`${dayLabel} 표시`}
                                className="mt-1 h-4 w-4 rounded border-hairline text-primary focus:ring-primary"
                              />
                              <div className="min-w-0 flex-1">
                                <div className="flex items-start gap-2">
                                  <button
                                    type="button"
                                    role="tab"
                                    aria-label={dayLabel}
                                    aria-selected={active}
                                    onClick={() => handleSelectDay(day.day_index)}
                                    className="min-w-0 flex-1 text-left"
                                  >
                                    <span className="flex min-w-0 items-center gap-2">
                                      <span className="truncate text-sm font-bold text-ink">
                                        {dayLabel}
                                      </span>
                                      <span className="shrink-0 rounded-sm bg-surface-soft px-1.5 py-0.5 text-[11px] font-semibold text-muted">
                                        {day.pois.length}곳
                                      </span>
                                    </span>
                                    <span className="mt-1 block text-xs text-muted">
                                      {/* ADR-055: date는 override-only → effective_date 표시. */}
                                      {formatTripDate(day.effective_date ?? day.date)} ·{' '}
                                      {visible ? '표시' : '숨김'}
                                    </span>
                                    {day.out_of_range && (
                                      <span
                                        className="mt-1 inline-flex w-fit items-center gap-1 rounded-sm bg-error-bg px-1.5 py-0.5 text-[11px] font-semibold text-error-text"
                                        data-testid="trip-day-out-of-range"
                                        title="이 일자의 날짜가 여행 기간을 벗어났습니다."
                                      >
                                        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                                        기간 벗어남
                                      </span>
                                    )}
                                    {dayHolidayLabel && (
                                      <span
                                        className="mt-1 inline-flex w-fit rounded-sm bg-error-bg px-1.5 py-0.5 text-[11px] font-semibold text-error-text"
                                        data-testid="trip-day-holiday"
                                      >
                                        {dayHolidayLabel}
                                      </span>
                                    )}
                                  </button>
                                  <TripDayControls
                                    selectedDay={day}
                                    onAdd={handleAddDay}
                                    onUpdate={handleUpdateDay}
                                    onDelete={handleDeleteDay}
                                    showAdd={false}
                                    busy={busy}
                                  />
                                </div>
                              </div>
                            </div>

                            {active ? (
                              <div className="space-y-3 px-3 pb-3">
                                {/* 일자 탭이 이미 날짜/공휴일/기간-벗어남을 보이므로 여기선 일출/일몰만. */}
                                <TripDayHeader day={day} showSummary={false} />
                                <TripWeatherSummary
                                  featureId={day.pois[0]?.feature_id ?? null}
                                  date={day.date}
                                  label="날짜 날씨"
                                  compact={mobileWebLayout}
                                />
                                <TripAttachments
                                  tripId={tripId}
                                  dayIndex={day.day_index}
                                  title={`${day.day_index}일차 파일`}
                                  compact
                                />
                                <MapSearchBox onSelect={handleAddPlace} />
                                <TripDayOptimize
                                  tripId={tripId}
                                  dayIndex={day.day_index}
                                  poiCount={day.pois.length}
                                  onApplied={reload}
                                />
                                {mutationError && (
                                  <p
                                    role="alert"
                                    className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text"
                                    data-testid="poi-mutation-error"
                                  >
                                    {mutationError}
                                  </p>
                                )}
                                {addNotice && !mutationError && (
                                  <p
                                    role="status"
                                    className="rounded-sm bg-primary/10 px-3 py-2 text-xs text-primary"
                                    data-testid="poi-add-notice"
                                  >
                                    {addNotice}
                                  </p>
                                )}
                                <TripPoiList
                                  pois={day.pois}
                                  selectedPoiId={selectedPoiId}
                                  onSelectPoi={handleSelectPoi}
                                  tripId={tripId}
                                  dayDate={day.date}
                                  showInlineAttachments
                                  showWeather
                                  compact={mobileWebLayout}
                                  editable={!busy}
                                  onReorder={handleReorder}
                                  onEditPoi={handleEditPoi}
                                  onDelete={handleDelete}
                                  savingPoiId={savingPoiId}
                                  editingPoiId={editingPoiId}
                                  onEditToggle={setEditingPoiId}
                                />
                              </div>
                            ) : (
                              <div className="space-y-1 px-3 pb-2">
                                {day.pois.length > 0 &&
                                  day.pois.slice(0, 4).map((poi, index) => (
                                    <button
                                      key={poi.poi_id}
                                      type="button"
                                      onClick={() => handleSelectPoi(poi.poi_id)}
                                      className="flex w-full items-center gap-2 rounded-sm px-1 py-1 text-left hover:bg-surface-soft"
                                    >
                                      <span
                                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white"
                                        style={{ backgroundColor: paletteHex(poi.marker_color) }}
                                        aria-hidden="true"
                                      >
                                        {index + 1}
                                      </span>
                                      <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink">
                                        {poi.title ?? poi.feature_id ?? '장소'}
                                      </span>
                                    </button>
                                  ))}
                                {day.pois.length > 4 && (
                                  <p className="pl-7 text-[11px] text-muted">
                                    외 {day.pois.length - 4}곳
                                  </p>
                                )}
                              </div>
                            )}
                          </article>
                        );
                      })}
                    </div>
                  )}
                </section>
              </div>
            )}

            {activePanel === 'files' && (
              <div
                id="trip-panel-files"
                role="tabpanel"
                aria-label="파일"
                className="space-y-4 p-4 md:p-5"
              >
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
                <TripAttachments tripId={tripId} />
              </div>
            )}

            {activePanel === 'share' && (
              <div
                id="trip-panel-share"
                role="tabpanel"
                aria-label="공유"
                className="space-y-4 p-4 md:p-5"
              >
                <div id="trip-share-section">
                  <TripShareLinks
                    tripId={tripId}
                    shareLinks={view.share_links}
                    onChanged={reload}
                  />
                </div>
                <TripTelegramTargets tripId={tripId} />
              </div>
            )}

            {activePanel === 'people' && (
              <div
                id="trip-panel-people"
                role="tabpanel"
                aria-label="동행"
                className="space-y-4 p-4 md:p-5"
              >
                <TripCompanions tripId={tripId} companions={companions} onChanged={reload} />
              </div>
            )}

            {activePanel === 'comments' && (
              <div
                id="trip-panel-comments"
                role="tabpanel"
                aria-label="댓글"
                className="space-y-4 p-4 md:p-5"
              >
                <TripComments tripId={tripId} />
              </div>
            )}
          </div>
        </aside>

        <section
          id="trip-map-canvas"
          className={
            mobileWebLayout
              ? 'relative min-h-0 flex-1 bg-canvas'
              : 'relative min-h-[calc(100svh-10rem)] flex-1 bg-canvas lg:h-full lg:min-h-0'
          }
          aria-label="여행 지도"
          data-testid="trip-detail-map"
        >
          <div
            className={
              mobileWebLayout
                ? 'pointer-events-none absolute left-2 right-2 top-20 z-10'
                : 'pointer-events-none absolute left-3 right-3 top-3 z-10 md:left-4 md:right-auto md:w-[min(560px,calc(100%-2rem))]'
            }
          >
            <div
              className="pointer-events-auto rounded-sm border border-hairline bg-white/95 p-2 shadow-card backdrop-blur"
              data-testid="trip-map-place-search"
            >
              {selectedDay ? (
                <MapSearchBox onSelect={handleAddPlace} />
              ) : (
                <p className="px-2 py-1 text-sm text-muted">선택된 일자가 없습니다.</p>
              )}
            </div>
          </div>
          <TripMapView
            apiKey={VWORLD_API_KEY}
            points={mapPoints}
            selectedPoiId={selectedPoiId}
            showFeatures
            hiddenFeatureIds={plannedFeatureIds}
            canAddFeature={selectedDay != null && !busy}
            onSelectPoi={handleSelectPoi}
            onMarkerContextMenu={handleMarkerContextMenu}
            onAddFeature={handleAddFeature}
            onCreatePoiAtCoordinate={handleCreatePoiAtCoordinate}
            showNavigationControls={!mobileWebLayout}
            className="h-full"
            chrome="flush"
          />
          <div
            data-testid="trip-map-stats"
            className={
              mobileWebLayout
                ? 'pointer-events-none absolute bottom-16 left-3 z-10 flex flex-wrap gap-2'
                : 'pointer-events-none absolute bottom-3 left-3 z-10 flex flex-wrap gap-2 md:bottom-4 md:left-4'
            }
          >
            <span className="rounded-sm bg-white/95 px-3 py-2 text-xs font-semibold text-ink shadow-card">
              {visibleLayerCount}일 표시
            </span>
            <span className="rounded-sm bg-white/95 px-3 py-2 text-xs font-semibold text-ink shadow-card">
              장소 {mapPoints.length}곳
            </span>
          </div>
        </section>
      </div>

      {tripEditOpen && (
        <TripEditDialog
          trip={trip}
          saving={busy}
          error={mutationError}
          onSave={handleEditTrip}
          onClose={() => setTripEditOpen(false)}
        />
      )}

      {manualPoiCoord && selectedDay && (
        <TripManualPoiDialog
          coord={manualPoiCoord}
          dayLabel={selectedDay.title ?? `${selectedDay.day_index}일차`}
          saving={busy}
          error={mutationError}
          onClose={() => setManualPoiCoord(null)}
          onCreate={handleCreateManualPoi}
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

      {/* ADR-055 F2: POI가 있는 일자 삭제 경고 — 확인 시 force로 함께 삭제. */}
      <ConfirmDialog
        open={dayDeleteConfirm != null}
        tone="danger"
        title={`${dayDeleteConfirm?.dayIndex ?? ''}일차를 삭제할까요?`}
        description={
          dayDeleteConfirm
            ? `이 일자에는 POI ${dayDeleteConfirm.poiCount}곳이 있습니다. 삭제하면 함께 제거되며 되돌릴 수 없습니다.`
            : undefined
        }
        confirmLabel="일자와 POI 삭제"
        cancelLabel="취소"
        busy={busy}
        onConfirm={confirmForceDeleteDay}
        onCancel={() => setDayDeleteConfirm(null)}
        testId="day-delete-confirm"
      />
    </div>
  );
}
