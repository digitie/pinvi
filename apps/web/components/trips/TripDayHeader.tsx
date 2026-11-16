'use client';

import { AlertTriangle, Sunrise, Sunset } from 'lucide-react';
import type { TripDayHoliday, TripViewDay } from '@pinvi/schemas';
import { formatKstTime, formatTripDate, tripDayTone, tripWeekday } from '@/lib/tripDateLabels';

/**
 * 날짜 + 요일 — 일요일·공휴일은 빨강, 토요일은 파랑(달력 관례, 2026-11-16 소유자 요청 17).
 * 공휴일 이름은 호출부가 따로 뱃지로 보인다(KASI 특일 `is_holiday`, PinVi ETL `kasi_special_days_job`).
 */
export function TripDayDateLabel({
  value,
  holidays,
  className,
}: {
  value: string | null;
  holidays?: TripDayHoliday[];
  className?: string;
}) {
  const weekday = tripWeekday(value);
  const tone = tripDayTone(value, holidays);
  return (
    <span className={className} data-testid="trip-day-date" data-day-tone={tone ?? undefined}>
      {formatTripDate(value)}
      {weekday && (
        <span
          className={
            tone === 'holiday'
              ? 'ml-1 font-semibold text-error-text'
              : tone === 'saturday'
                ? 'ml-1 font-semibold text-legal-link'
                : 'ml-1'
          }
          data-testid="trip-day-weekday"
        >
          ({weekday.label})
        </span>
      )}
    </span>
  );
}

export interface TripDayHeaderProps {
  day: Pick<
    TripViewDay,
    | 'day_index'
    | 'date'
    | 'effective_date'
    | 'out_of_range'
    | 'holidays'
    | 'rise_set'
    | 'rise_set_reference'
  > & { note?: string | null };
  className?: string;
  /**
   * false면 날짜/공휴일/기간-벗어남 요약 행을 숨기고 일출/일몰만 표시한다.
   * 호출부(예: `TripDetail`의 일자 탭)가 이미 그 요약을 렌더할 때 중복을 피하기 위함.
   */
  showSummary?: boolean;
  /** 읽기 전용(공유 화면) — 대기 안내를 편집 지시 없이 중립 문구로. */
  readOnly?: boolean;
}

/**
 * 일자 요약 헤더(ADR-055 §6, F8) — effective date + 공휴일 + 기간 벗어남 + 일출/일몰.
 * owner(`TripDetail`)와 공유 뷰(`SharedTripView`)가 공용으로 쓴다(순수 표현).
 */
export function TripDayHeader({
  day,
  className,
  showSummary = true,
  readOnly = false,
}: TripDayHeaderProps) {
  const holidayNames = Array.from(new Set(day.holidays.map((h) => h.name).filter(Boolean)));
  return (
    <div className={className} data-testid="trip-day-header">
      {showSummary && (
        <div className="flex flex-wrap items-center gap-2">
          <TripDayDateLabel
            value={day.effective_date ?? day.date}
            holidays={day.holidays}
            className="text-sm font-semibold text-ink"
          />
          {day.out_of_range && (
            <span
              className="inline-flex items-center gap-1 rounded-sm bg-error-bg px-1.5 py-0.5 text-xs font-semibold text-error-text"
              data-testid="trip-day-header-out-of-range"
              title="이 일자의 날짜가 여행 기간을 벗어났습니다."
            >
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              기간 벗어남
            </span>
          )}
          {holidayNames.map((name) => (
            <span
              key={name}
              className="inline-flex rounded-sm bg-error-bg px-1.5 py-0.5 text-xs font-semibold text-error-text"
              data-testid="trip-day-header-holiday"
            >
              {name}
            </span>
          ))}
        </div>
      )}
      {day.note && (
        <p
          className="mt-2 whitespace-pre-wrap break-words text-sm text-body"
          data-testid="trip-day-note"
        >
          {day.note}
        </p>
      )}
      <TripDayRiseSet day={day} readOnly={readOnly} />
    </div>
  );
}

/**
 * 장소 좌표 기준 일출·일몰 한 줄(장소 날씨 아래) — 서버가 astral로 계산한 `poi.rise_set`(요청 18).
 * 계산되지 않은 상태(pending_*·failed)는 아무것도 보이지 않는다(일자 머리글이 안내를 맡는다).
 */
export function PoiRiseSetLine({ riseSet }: { riseSet: TripViewDay['rise_set'] | undefined }) {
  const sunrise = formatKstTime(riseSet?.sunrise_at);
  const sunset = formatKstTime(riseSet?.sunset_at);
  if (riseSet?.status !== 'success' || (!sunrise && !sunset)) return null;
  return (
    <p
      className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted"
      data-testid="trip-poi-rise-set"
    >
      {sunrise && (
        <span className="inline-flex items-center gap-1">
          <Sunrise className="h-3.5 w-3.5" aria-hidden="true" />
          일출 {sunrise}
        </span>
      )}
      {sunset && (
        <span className="inline-flex items-center gap-1">
          <Sunset className="h-3.5 w-3.5" aria-hidden="true" />
          일몰 {sunset}
        </span>
      )}
    </p>
  );
}

function TripDayRiseSet({ day, readOnly }: { day: TripDayHeaderProps['day']; readOnly: boolean }) {
  const rs = day.rise_set;
  const reference = day.rise_set_reference;
  const sunrise = formatKstTime(rs?.sunrise_at);
  const sunset = formatKstTime(rs?.sunset_at);

  // 성공 + 시각이 있으면 일출/일몰을 표시, 아니면 준비 중 안내(좌표/날짜 미확정 등).
  if (rs?.status === 'success' && (sunrise || sunset)) {
    return (
      <div
        className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted"
        data-testid="trip-day-rise-set"
      >
        {sunrise && (
          <span className="inline-flex items-center gap-1">
            <Sunrise className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            일출 {sunrise}
          </span>
        )}
        {sunset && (
          <span className="inline-flex items-center gap-1">
            <Sunset className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            일몰 {sunset}
          </span>
        )}
        {reference && <span className="text-muted">{reference} 기준</span>}
      </div>
    );
  }
  // 준비 중(pending_*)일 때만 안내. failed / success-무값 / null은 표시하지 않는다(잘못된 "준비 중" 방지).
  // 무엇을 기다리는지에 따라 문구를 나눈다 — 장소가 없는 날에 "준비 중"이라고 하면 사용자는 기다리기만
  // 한다(2026-11-02 prod e2e: 빈 일자가 계속 "일출·일몰 준비 중"이었다). 상태는 `trip_day_rise_set.py`
  // `_status_for`가 정한다.
  if (rs != null && rs.status.startsWith('pending')) {
    return (
      <p
        className="mt-1 text-xs text-muted"
        data-testid="trip-day-rise-set-pending"
        data-rise-set-status={rs.status}
      >
        {risePendingMessage(rs.status, readOnly)}
      </p>
    );
  }
  return null;
}

function risePendingMessage(
  status: NonNullable<TripViewDay['rise_set']>['status'],
  readOnly: boolean,
): string {
  // 공유(읽기 전용) 화면에서는 "추가하세요" 같은 편집 안내 대신 중립 문구를 쓴다.
  if (readOnly) return status === 'pending_fetch' ? '일출·일몰 준비 중' : '일출·일몰 정보 없음';
  // pending_coord는 장소가 아예 없거나, 있어도 좌표가 하나도 없을 때다(`trip_day_rise_set._status_for`).
  if (status === 'pending_coord') return '좌표가 있는 장소를 추가하면 일출·일몰을 표시합니다';
  if (status === 'pending_date') return '날짜를 정하면 일출·일몰을 표시합니다';
  return '일출·일몰 준비 중';
}
