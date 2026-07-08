'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CalendarDays,
  Loader2,
  Map as MapIcon,
  MapPin,
  RefreshCw,
  Save,
  SlidersHorizontal,
} from 'lucide-react';
import { ApiError, tripApi, type TripBucket } from '@pinvi/api-client';
import type { TripCreate, TripResponse, TripStatus } from '@pinvi/schemas';
import { tripDaysToMapPoints, type TripMapPoint } from '@pinvi/domain';
import { apiClient } from '@/lib/api';
import { FormField } from '@/components/forms/FormField';
import { TripMapView } from '@/components/trips/TripMapView';

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? '';

const STATUS_LABEL: Record<TripStatus, string> = {
  draft: '초안',
  planned: '예정',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

const BUCKETS: { value: TripBucket; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'future', label: '예정' },
  { value: 'past', label: '지난 여행' },
];

type TripDashboardMapPoint = TripMapPoint & {
  tripId: string;
  tripTitle: string;
  tripRegion: string;
  tripDateRange: string;
  tripStatus: TripStatus;
};

function formatDate(value: string | null): string {
  if (!value) {
    return '미정';
  }
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value));
}

function formatDateRange(trip: Pick<TripResponse, 'start_date' | 'end_date'>): string {
  return `${formatDate(trip.start_date)} - ${formatDate(trip.end_date)}`;
}

function tripRegion(trip: Pick<TripResponse, 'region_hint' | 'primary_region_code'>): string {
  return trip.region_hint ?? trip.primary_region_code ?? '지역 미정';
}

function isPastTrip(trip: TripResponse): boolean {
  if (!trip.end_date) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return new Date(`${trip.end_date}T00:00:00`) < today;
}

function visibleTrips(trips: TripResponse[], bucket: TripBucket): TripResponse[] {
  if (bucket === 'all') {
    return trips;
  }
  return trips.filter((trip) => (bucket === 'past' ? isPastTrip(trip) : !isPastTrip(trip)));
}

function validateDateRange(startDate: string, endDate: string): string | null {
  if (!startDate && !endDate) {
    return null;
  }
  if (!startDate || !endDate) {
    return '시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.';
  }
  if (endDate < startDate) {
    return '종료일은 시작일 이후여야 합니다.';
  }
  return null;
}

export function TripDashboard() {
  const [trips, setTrips] = useState<TripResponse[]>([]);
  const [bucket, setBucket] = useState<TripBucket>('all');
  const [loading, setLoading] = useState(true);
  const [mapLoading, setMapLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [regionHint, setRegionHint] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [titleError, setTitleError] = useState<string | undefined>(undefined);
  const [dateError, setDateError] = useState<string | undefined>(undefined);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [mobileToolsOpen, setMobileToolsOpen] = useState(false);
  const [mapPointsByTripId, setMapPointsByTripId] = useState<
    Record<string, TripDashboardMapPoint[]>
  >({});
  const titleRef = useRef<HTMLInputElement>(null);
  const mapRequestIdRef = useRef(0);

  const filteredTrips = useMemo(() => visibleTrips(trips, bucket), [bucket, trips]);
  const filteredMapPoints = useMemo(
    () => filteredTrips.flatMap((trip) => mapPointsByTripId[trip.trip_id] ?? []),
    [filteredTrips, mapPointsByTripId],
  );
  const upcomingCount = useMemo(() => trips.filter((trip) => !isPastTrip(trip)).length, [trips]);
  const draftCount = useMemo(() => trips.filter((trip) => trip.status === 'draft').length, [trips]);
  const selectedMapPoint = useMemo(
    () => filteredMapPoints.find((point) => point.poiId === selectedPoiId) ?? null,
    [filteredMapPoints, selectedPoiId],
  );

  useEffect(() => {
    if (selectedPoiId && !filteredMapPoints.some((point) => point.poiId === selectedPoiId)) {
      setSelectedPoiId(null);
    }
  }, [filteredMapPoints, selectedPoiId]);

  const loadTripMapPoints = useCallback(async (items: TripResponse[]) => {
    const requestId = ++mapRequestIdRef.current;
    setMapError(null);
    setMapPointsByTripId({});

    if (items.length === 0) {
      setMapLoading(false);
      return;
    }

    setMapLoading(true);
    const api = tripApi(apiClient);
    const results = await Promise.allSettled(
      items.map(async (trip) => {
        const view = await api.get(trip.trip_id);
        const points: TripDashboardMapPoint[] = tripDaysToMapPoints(view.days).map((point) => ({
          ...point,
          tripId: trip.trip_id,
          tripTitle: trip.title,
          tripRegion: tripRegion(trip),
          tripDateRange: formatDateRange(trip),
          tripStatus: trip.status,
        }));
        return [trip.trip_id, points] as const;
      }),
    );

    if (mapRequestIdRef.current !== requestId) {
      return;
    }

    const next: Record<string, TripDashboardMapPoint[]> = {};
    let failed = 0;
    for (const result of results) {
      if (result.status === 'fulfilled') {
        next[result.value[0]] = result.value[1];
      } else {
        failed += 1;
      }
    }

    setMapPointsByTripId(next);
    setMapError(failed > 0 ? '일부 여행 장소를 지도에 표시하지 못했습니다.' : null);
    setMapLoading(false);
  }, []);

  const loadTrips = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await tripApi(apiClient).list({ bucket: 'all', limit: 50 });
      setTrips(items);
      void loadTripMapPoints(items);
    } catch (err) {
      setTrips([]);
      setMapPointsByTripId({});
      setMapLoading(false);
      setError(err instanceof ApiError ? err.message : '여행 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [loadTripMapPoints]);

  useEffect(() => {
    void loadTrips();
  }, [loadTrips]);

  const onCreate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedTitle = title.trim();
    const nextDateError = validateDateRange(startDate, endDate);
    if (!trimmedTitle) {
      setTitleError('여행 제목을 입력하세요.');
      titleRef.current?.focus();
      return;
    }
    if (nextDateError) {
      setTitleError(undefined);
      setDateError(nextDateError);
      return;
    }
    setTitleError(undefined);
    setDateError(undefined);
    setCreating(true);
    setError(null);
    setMessage(null);
    const body: TripCreate = {
      title: trimmedTitle,
      description: null,
      region_hint: regionHint.trim() || null,
      start_date: startDate || null,
      end_date: endDate || null,
      visibility: 'private',
      companions: [],
    };
    try {
      const created = await tripApi(apiClient).create(body);
      setTrips((current) => [created, ...current]);
      setMapPointsByTripId((current) => ({ ...current, [created.trip_id]: [] }));
      setBucket('all');
      setTitle('');
      setRegionHint('');
      setStartDate('');
      setEndDate('');
      setMessage('초안 여행을 저장했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '여행을 저장하지 못했습니다.');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 border-b border-hairline pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-primary">Trips</p>
          <h1 className="mt-1 text-2xl font-bold text-ink md:text-3xl">여행</h1>
          <p className="mt-2 text-sm text-muted">
            전체 {trips.length} · 예정 {upcomingCount} · 초안 {draftCount}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setMobileToolsOpen((open) => !open)}
            aria-controls="trip-dashboard-create"
            aria-expanded={mobileToolsOpen}
            className="inline-flex h-10 w-fit items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft lg:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            {mobileToolsOpen ? '관리 닫기' : '관리 열기'}
          </button>
          <button
            type="button"
            onClick={() => void loadTrips()}
            className="inline-flex h-10 w-fit items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            )}
            새로고침
          </button>
        </div>
      </header>

      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="trips-error"
        >
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section
          className="relative hidden min-h-[calc(100svh-14rem)] lg:block lg:min-h-[560px]"
          aria-label="전체 여행 지도"
        >
          <TripMapView
            apiKey={VWORLD_API_KEY}
            points={filteredMapPoints}
            selectedPoiId={selectedPoiId}
            onSelectPoi={setSelectedPoiId}
            className="h-[calc(100svh-14rem)] min-h-[520px] lg:h-[calc(100vh-14rem)]"
          />

          <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-2">
            <span className="rounded-sm bg-white/95 px-3 py-2 text-xs font-semibold text-ink shadow-card">
              {filteredTrips.length}개 여행
            </span>
            <span className="rounded-sm bg-white/95 px-3 py-2 text-xs font-semibold text-ink shadow-card">
              {mapLoading ? '장소 불러오는 중' : `${filteredMapPoints.length}개 장소`}
            </span>
          </div>

          {(mapError || selectedMapPoint) && (
            <div className="pointer-events-auto absolute bottom-3 left-3 right-3 max-w-md rounded-sm border border-hairline bg-white/95 p-3 shadow-card">
              {mapError && <p className="text-xs text-error-text">{mapError}</p>}
              {selectedMapPoint && (
                <div className={mapError ? 'mt-2 border-t border-hairline pt-2' : ''}>
                  <p className="text-sm font-semibold text-ink">{selectedMapPoint.title}</p>
                  <p className="mt-1 text-xs text-muted">
                    {selectedMapPoint.tripTitle} · {selectedMapPoint.tripRegion} ·{' '}
                    {selectedMapPoint.tripDateRange}
                  </p>
                  <Link
                    href={`/trips/${selectedMapPoint.tripId}`}
                    className="mt-2 inline-flex h-8 items-center rounded-sm bg-primary px-3 text-xs font-semibold text-white"
                  >
                    여행 열기
                  </Link>
                </div>
              )}
            </div>
          )}
        </section>

        <aside
          className="space-y-4"
          aria-label="여행 관리"
        >
          <section
            id="trip-dashboard-create"
            className={`${mobileToolsOpen ? 'block' : 'hidden'} rounded-sm border border-hairline bg-white p-4 lg:block`}
          >
            <form onSubmit={onCreate} className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-bold text-ink">
                <Save className="h-4 w-4 text-primary" aria-hidden="true" />새 여행 저장
              </div>
              <FormField
                ref={titleRef}
                id="trip-create-title"
                label="제목"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="h-10 focus:border-primary"
                maxLength={200}
                placeholder="부산 2박 3일"
                error={titleError}
                data-testid="trip-create-title"
              />
              <FormField
                id="trip-create-region"
                label="지역"
                value={regionHint}
                onChange={(event) => setRegionHint(event.target.value)}
                className="h-10 focus:border-primary"
                maxLength={120}
                placeholder="부산"
                data-testid="trip-create-region"
              />
              <div className="grid grid-cols-2 gap-2">
                <FormField
                  id="trip-create-start"
                  label="시작일"
                  type="date"
                  value={startDate}
                  onChange={(event) => {
                    setStartDate(event.target.value);
                    setDateError(undefined);
                  }}
                  className="h-10 focus:border-primary"
                  data-testid="trip-create-start"
                />
                <FormField
                  id="trip-create-end"
                  label="종료일"
                  type="date"
                  value={endDate}
                  onChange={(event) => {
                    setEndDate(event.target.value);
                    setDateError(undefined);
                  }}
                  error={dateError}
                  className="h-10 focus:border-primary"
                  data-testid="trip-create-end"
                />
              </div>
              <button
                type="submit"
                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
                disabled={creating}
                data-testid="trip-create-submit"
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Save className="h-4 w-4" aria-hidden="true" />
                )}
                초안 저장
              </button>
            </form>
          </section>

          <section className="space-y-3">
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="여행 필터">
              {BUCKETS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setBucket(item.value)}
                  className={
                    bucket === item.value
                      ? 'h-9 rounded-sm bg-ink px-3 text-sm font-semibold text-white'
                      : 'h-9 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft'
                  }
                  role="tab"
                  aria-selected={bucket === item.value}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {loading ? (
              <div className="flex min-h-48 items-center justify-center rounded-sm border border-hairline bg-white text-sm text-muted">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                불러오는 중...
              </div>
            ) : filteredTrips.length === 0 ? (
              <div className="flex min-h-48 flex-col items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center">
                <CalendarDays className="h-8 w-8 text-muted" aria-hidden="true" />
                <p className="mt-3 text-sm font-semibold text-ink">표시할 여행이 없습니다.</p>
                <p className="mt-1 text-xs text-muted">첫 여행을 저장하면 이곳에 나타납니다.</p>
              </div>
            ) : (
              <div className="space-y-2" data-testid="trip-list">
                {filteredTrips.map((trip) => {
                  const tripPointCount = mapPointsByTripId[trip.trip_id]?.length ?? 0;
                  const selected = selectedMapPoint?.tripId === trip.trip_id;
                  return (
                    <Link
                      key={trip.trip_id}
                      href={`/trips/${trip.trip_id}`}
                      className={
                        selected
                          ? 'block rounded-sm border border-primary bg-white p-4 shadow-card'
                          : 'block rounded-sm border border-hairline bg-white p-4 transition hover:border-primary hover:bg-surface-soft'
                      }
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h2 className="truncate text-base font-bold text-ink">{trip.title}</h2>
                          <p className="mt-1 flex items-center gap-1 text-sm text-muted">
                            <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                            <span className="truncate">{tripRegion(trip)}</span>
                          </p>
                        </div>
                        <span className="shrink-0 rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
                          {STATUS_LABEL[trip.status]}
                        </span>
                      </div>
                      <p className="mt-3 flex items-center gap-1 text-sm text-body">
                        <CalendarDays className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                        {formatDateRange(trip)}
                      </p>
                      <p className="mt-2 flex items-center gap-1 text-xs text-muted">
                        <MapIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        지도 장소 {tripPointCount}개
                      </p>
                      {trip.description && (
                        <p className="mt-2 line-clamp-2 text-sm text-muted">{trip.description}</p>
                      )}
                      <span className="mt-3 inline-flex h-8 items-center rounded-sm border border-hairline px-3 text-xs font-semibold text-ink">
                        열기/업데이트
                      </span>
                    </Link>
                  );
                })}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
