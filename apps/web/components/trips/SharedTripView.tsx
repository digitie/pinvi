'use client';

import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Loader2, MapPin } from 'lucide-react';
import { ApiError, tripApi } from '@pinvi/api-client';
import type { TripSharedView } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { tripDaysToMapPoints } from '@pinvi/domain';
import { TripDayHeader } from '@/components/trips/TripDayHeader';
import { TripMapView } from '@/components/trips/TripMapView';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { ButtonLink } from '@/components/ui/Button';
import { formatTripDateRange, holidayLabel, holidaysByDate } from '@/lib/tripDateLabels';

const VWORLD_API_KEY = process.env.NEXT_PUBLIC_VWORLD_API_KEY ?? '';

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
  const holidayMap = useMemo(() => holidaysByDate(view?.days ?? []), [view?.days]);

  const handleSelectPoi = (poiId: string) => {
    setSelectedPoiId(poiId);
    const dayIndex = poiDay.get(poiId);
    if (dayIndex != null) setSelectedDayIndex(dayIndex);
  };

  if (loading) {
    return (
      <div
        className="flex min-h-64 items-center justify-center rounded-sm bg-surface-soft text-sm text-muted"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        여행을 불러오는 중…
      </div>
    );
  }

  if (error || !view) {
    // 오류는 dead end가 아니라 원인 + 다음 행동(홈/로그인) — 404 페이지와 같은 구조·언어.
    return (
      <section
        className="max-w-md space-y-6 border-t-2 border-ink pt-6"
        aria-labelledby="shared-error-title"
        data-testid="shared-error"
      >
        <div className="space-y-2">
          <h1 id="shared-error-title" className="text-2xl font-bold tracking-tight text-ink">
            공유 링크를 열 수 없어요
          </h1>
          <p className="text-base text-body" role="alert">
            {error ?? '공유 링크가 만료되었거나 유효하지 않습니다.'} 링크를 보낸 사람에게 새 링크를
            요청하거나, 내 여행에서 직접 확인해 주세요.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <ButtonLink href="/" variant="primary">
            홈으로
          </ButtonLink>
          <ButtonLink href="/login" variant="secondary">
            로그인
          </ButtonLink>
        </div>
      </section>
    );
  }

  const { trip } = view;

  return (
    <div className="space-y-5">
      <header className="space-y-2 border-b border-hairline pb-4">
        <p className="text-sm text-muted">공유된 여행 · 읽기 전용</p>
        <h1 className="text-2xl font-bold tracking-tight text-ink [overflow-wrap:anywhere] md:text-3xl">
          {trip.title}
        </h1>
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <span className="inline-flex items-center gap-1">
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
            {formatTripDateRange(trip.start_date, trip.end_date, holidayMap)}
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
            const dayHolidayLabel = holidayLabel(day.holidays);
            return (
              <button
                key={day.day_index}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setSelectedDayIndex(day.day_index)}
                className={
                  active
                    ? 'focus-ring min-h-11 rounded-sm bg-ink px-3 text-sm font-semibold text-on-primary'
                    : 'focus-ring min-h-11 rounded-sm border border-hairline bg-canvas px-3 text-sm font-semibold text-ink hover:bg-surface-soft'
                }
              >
                {day.title ?? `${day.day_index}일차`}
                {dayHolidayLabel && (
                  <span className="ml-2 text-xs opacity-85">{dayHolidayLabel}</span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {selectedDay && (
        <TripDayHeader day={selectedDay} className="mb-3 rounded-sm bg-surface-soft p-3" />
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
            dayDate={selectedDay?.effective_date ?? selectedDay?.date ?? null}
            weatherCards={selectedDay?.weather_cards}
            weatherByFeatureId={selectedDay?.weather_by_feature_id}
            showWeather
          />
        </aside>
      </div>
    </div>
  );
}
