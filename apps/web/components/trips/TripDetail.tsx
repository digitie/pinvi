'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowLeft, CalendarDays, Loader2, MapPin, Users } from 'lucide-react';
import { ApiError, poiApi, tripApi } from '@tripmate/api-client';
import type { FeatureSummary, TripStatus, TripView } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import type { MarkerColorKey } from '@/lib/markerPalette';
import { appendRank, reorderMoves } from '@/lib/poiRank';
import { tripDaysToMapPoints } from '@/lib/tripMapPoints';
import { MapSearchBox } from '@/components/map/MapSearchBox';
import { TripDayControls } from '@/components/trips/TripDayControls';
import { TripMapView } from '@/components/trips/TripMapView';
import { TripPoiList } from '@/components/trips/TripPoiList';

const STATUS_LABEL: Record<TripStatus, string> = {
  draft: '초안',
  planned: '예정',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? '';

function formatDate(value: string | null): string {
  if (!value) return '미정';
  return new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }).format(
    new Date(value)
  );
}

export interface TripDetailProps {
  tripId: string;
}

export function TripDetail({ tripId }: TripDetailProps) {
  const [view, setView] = useState<TripView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [savingPoiId, setSavingPoiId] = useState<string | null>(null);
  const [editingPoiId, setEditingPoiId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async (): Promise<TripView | null> => {
    try {
      const res = await tripApi(apiClient).get(tripId);
      setView(res);
      setError(null);
      return res;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '여행을 불러오지 못했습니다.');
      return null;
    }
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

  const mapPoints = useMemo(() => (view ? tripDaysToMapPoints(view.days) : []), [view]);
  const poiDay = useMemo(() => {
    const map = new Map<string, number>();
    for (const point of mapPoints) map.set(point.poiId, point.dayIndex);
    return map;
  }, [mapPoints]);

  const selectedDay = view?.days.find((day) => day.day_index === selectedDayIndex) ?? null;

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
    async (fn: () => Promise<unknown>) => {
      setMutationError(null);
      setBusy(true);
      try {
        await fn();
        await reload();
      } catch (err) {
        setMutationError(err instanceof ApiError ? err.message : '변경에 실패했습니다.');
        await reload();
      } finally {
        setBusy(false);
      }
    },
    [reload]
  );

  const handleAddFeature = (feature: FeatureSummary) => {
    if (selectedDay == null) return;
    const last = selectedDay.pois[selectedDay.pois.length - 1]?.sort_order ?? null;
    void runMutation(() =>
      poiApi(apiClient).create(tripId, {
        day_index: selectedDay.day_index,
        sort_order: appendRank(last),
        feature_id: feature.feature_id,
        feature_snapshot: {
          coord: { lon: feature.coord.lon, lat: feature.coord.lat },
          title: feature.title,
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

  const handleEditMarker = (
    poi: { poi_id: string; version: number },
    color: MarkerColorKey,
    icon: string
  ) => {
    setSavingPoiId(poi.poi_id);
    void runMutation(() =>
      poiApi(apiClient).update(tripId, poi.poi_id, poi.version, {
        custom_marker_color: color,
        custom_marker_icon: icon,
      })
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
          <span className="shrink-0 rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
            {STATUS_LABEL[trip.status]}
          </span>
        </div>
        {view.broken_feature_count > 0 && (
          <p className="inline-flex items-center gap-1.5 rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            링크가 끊긴 장소 {view.broken_feature_count}곳 — 라이브러리에서 삭제됨
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
          {mutationError && (
            <p
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
            onEditMarker={handleEditMarker}
            onDelete={handleDelete}
            savingPoiId={savingPoiId}
            editingPoiId={editingPoiId}
            onEditToggle={setEditingPoiId}
          />
        </aside>
      </div>
    </div>
  );
}
