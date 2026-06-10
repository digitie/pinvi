'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Loader2, MapPin, Share2 } from 'lucide-react';
import { ApiError, tripApi } from '@tripmate/api-client';
import type { TripSharedView } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { tripDaysToMapPoints } from '@/lib/tripMapPoints';
import { TripMapView } from '@/components/trips/TripMapView';
import { TripPoiList } from '@/components/trips/TripPoiList';

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? '';

function formatDate(value: string | null): string {
  if (!value) return '미정';
  return new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'short', day: 'numeric' }).format(
    new Date(value)
  );
}

export interface SharedTripViewProps {
  tripId: string;
  token: string;
}

export function SharedTripView({ tripId, token }: SharedTripViewProps) {
  const [view, setView] = useState<TripSharedView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDayIndex, setSelectedDayIndex] = useState<number | null>(null);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    tripApi(apiClient)
      .getShared(tripId, token)
      .then((res) => {
        if (cancelled) return;
        setView(res);
        setSelectedDayIndex(res.days[0]?.day_index ?? null);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : '공유 여행을 불러오지 못했습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tripId, token]);

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
      <div className="space-y-3">
        <p
          role="alert"
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="shared-error"
        >
          {error ?? '공유 링크가 만료되었거나 유효하지 않습니다.'}
        </p>
        <Link href="/" className="inline-block text-sm font-semibold text-primary hover:underline">
          TripMate 홈으로
        </Link>
      </div>
    );
  }

  const { trip } = view;

  return (
    <div className="space-y-5">
      <header className="space-y-2 border-b border-hairline pb-4">
        <p className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-normal text-primary">
          <Share2 className="h-3.5 w-3.5" aria-hidden="true" />
          공유된 여행
        </p>
        <h1 className="truncate text-2xl font-bold text-ink md:text-3xl">{trip.title}</h1>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
            {formatDate(trip.start_date)} – {formatDate(trip.end_date)}
          </span>
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-4 w-4" aria-hidden="true" />
            {trip.region_hint ?? trip.primary_region_code ?? '지역 미정'}
          </span>
        </p>
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

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="min-h-[460px]" aria-label="여행 지도">
          <TripMapView
            apiKey={VWORLD_API_KEY}
            points={mapPoints}
            selectedPoiId={selectedPoiId}
            onSelectPoi={handleSelectPoi}
            className="h-full"
          />
        </section>
        <aside aria-label="장소 목록">
          <TripPoiList
            pois={selectedDay?.pois ?? []}
            selectedPoiId={selectedPoiId}
            onSelectPoi={handleSelectPoi}
          />
        </aside>
      </div>
    </div>
  );
}
