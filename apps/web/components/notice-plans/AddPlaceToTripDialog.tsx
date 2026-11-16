'use client';

import { Button, ButtonLink } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { apiClient } from '@/lib/api';
import { ApiError, poiApi, tripApi } from '@pinvi/api-client';
import { appendRank } from '@pinvi/domain';
import type { TripResponse, TripView } from '@pinvi/schemas';
import { CheckCircle2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

/* Hallmark · genre: modern-minimal · design-system: DESIGN.md
 * 추천 여행 주변 정보(축제·큐레이션)의 장소 1곳을 내 여행의 한 일자 끝에 넣는다.
 * 여행 → 일자 2단 선택. 행사는 시작일과 같은 날짜의 일자를 미리 고른다.
 */

export interface AddablePlace {
  feature_id: string;
  name: string;
  kind: string;
  category: string | null;
  lon: number;
  lat: number;
  marker_color?: string | null;
  marker_icon?: string | null;
  /** 이 날짜와 같은 일자를 기본 선택한다(행사 시작일). */
  preferred_date?: string | null;
}

export interface AddPlaceToTripDialogProps {
  place: AddablePlace;
  onClose: () => void;
}

function dayLabel(day: TripView['days'][number]): string {
  const date = day.effective_date ?? day.date;
  return date ? `${day.day_index}일차 · ${date}` : `${day.day_index}일차`;
}

export function AddPlaceToTripDialog({ place, onClose }: AddPlaceToTripDialogProps) {
  const [trips, setTrips] = useState<TripResponse[] | null>(null);
  const [tripId, setTripId] = useState<string | null>(null);
  const [view, setView] = useState<TripView | null>(null);
  const [dayIndex, setDayIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addedTripId, setAddedTripId] = useState<string | null>(null);
  const successCloseRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let cancelled = false;
    tripApi(apiClient)
      .list({ limit: 50 })
      .then((items) => {
        if (!cancelled) setTrips(items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTrips([]);
        setError(err instanceof ApiError ? err.message : '여행 목록을 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (tripId == null) return;
    let cancelled = false;
    tripApi(apiClient)
      .get(tripId)
      .then((loaded) => {
        if (cancelled) return;
        setView(loaded);
        const preferred = place.preferred_date
          ? loaded.days.find((day) => (day.effective_date ?? day.date) === place.preferred_date)
          : undefined;
        setDayIndex(preferred?.day_index ?? loaded.days[0]?.day_index ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : '여행 일정을 불러오지 못했습니다.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tripId, place.preferred_date]);

  useEffect(() => {
    if (addedTripId) successCloseRef.current?.focus();
  }, [addedTripId]);

  const chooseTrip = (id: string) => {
    setError(null);
    setView(null);
    setDayIndex(null);
    setTripId(id);
  };

  const selectedDay = view?.days.find((day) => day.day_index === dayIndex) ?? null;

  const add = async () => {
    if (tripId == null || selectedDay == null) return;
    setSaving(true);
    setError(null);
    try {
      const last = selectedDay.pois[selectedDay.pois.length - 1]?.sort_order ?? null;
      await poiApi(apiClient).create(tripId, {
        day_index: selectedDay.day_index,
        sort_order: appendRank(last),
        feature_id: place.feature_id,
        source: 'feature',
        feature_snapshot: {
          coord: { lon: place.lon, lat: place.lat },
          name: place.name,
          title: place.name,
          category: place.category,
          kind: place.kind,
          marker_color: place.marker_color ?? null,
          marker_icon: place.marker_icon ?? null,
        },
        currency: 'KRW',
      });
      setAddedTripId(tripId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '장소를 추가하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  const footer = addedTripId ? (
    <>
      <Button ref={successCloseRef} variant="secondary" onClick={onClose}>
        닫기
      </Button>
      <ButtonLink href={`/trips/${addedTripId}`}>여행 열기</ButtonLink>
    </>
  ) : (
    <>
      <Button variant="secondary" onClick={onClose} disabled={saving}>
        취소
      </Button>
      <Button
        onClick={() => void add()}
        disabled={selectedDay == null}
        loading={saving}
        data-testid="add-place-confirm"
      >
        추가
      </Button>
    </>
  );

  return (
    <Dialog
      open
      onClose={onClose}
      busy={saving}
      size="sm"
      title="내 여행에 추가"
      description={place.name}
      testId="add-place-dialog"
      footer={footer}
    >
      {addedTripId ? (
        <p
          className="flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text"
          role="status"
        >
          <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
          {selectedDay ? `${dayLabel(selectedDay)}에 추가했습니다.` : '추가했습니다.'}
        </p>
      ) : (
        <div className="space-y-4">
          <fieldset>
            <legend className="text-sm font-semibold text-ink">여행</legend>
            {trips == null ? (
              <div className="mt-2 space-y-2" aria-busy="true" aria-live="polite">
                <span className="sr-only">여행 목록을 불러오는 중…</span>
                {[0, 1].map((row) => (
                  <div key={row} className="h-11 animate-pulse rounded-sm bg-surface-soft" />
                ))}
              </div>
            ) : trips.length === 0 ? (
              <p className="mt-2 rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
                추가할 여행이 없습니다. 먼저 여행을 만들어 주세요.
              </p>
            ) : (
              <ul className="mt-2 max-h-40 space-y-1 overflow-auto">
                {trips.map((trip) => (
                  <li key={trip.trip_id}>
                    <button
                      type="button"
                      onClick={() => chooseTrip(trip.trip_id)}
                      aria-pressed={tripId === trip.trip_id}
                      className={
                        tripId === trip.trip_id
                          ? 'focus-ring block min-h-11 w-full rounded-sm border border-ink bg-surface-soft px-3 py-2 text-left text-sm font-medium text-ink'
                          : 'focus-ring block min-h-11 w-full rounded-sm border border-hairline px-3 py-2 text-left text-sm text-ink hover:bg-surface-soft'
                      }
                    >
                      {trip.title}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>

          {tripId != null ? (
            <fieldset>
              <legend className="text-sm font-semibold text-ink">일자</legend>
              {view == null ? (
                error ? null : (
                  <div
                    className="mt-2 h-11 animate-pulse rounded-sm bg-surface-soft"
                    aria-busy="true"
                  />
                )
              ) : view.days.length === 0 ? (
                <p className="mt-2 rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">
                  이 여행에는 일자가 없습니다. 여행에서 일자를 먼저 추가해 주세요.
                </p>
              ) : (
                <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="일자 선택">
                  {view.days.map((day) => (
                    <button
                      key={day.day_index}
                      type="button"
                      onClick={() => setDayIndex(day.day_index)}
                      aria-pressed={dayIndex === day.day_index}
                      className={
                        dayIndex === day.day_index
                          ? 'focus-ring inline-flex min-h-11 items-center rounded-sm bg-ink px-3 text-sm font-semibold text-canvas'
                          : 'focus-ring inline-flex min-h-11 items-center rounded-sm border border-hairline bg-canvas px-3 text-sm text-ink hover:bg-surface-soft'
                      }
                    >
                      {dayLabel(day)}
                    </button>
                  ))}
                </div>
              )}
            </fieldset>
          ) : null}

          {error ? (
            <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
              {error}
            </p>
          ) : null}
        </div>
      )}
    </Dialog>
  );
}
