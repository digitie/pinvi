// Trip 날짜/공휴일/시각 라벨 — 순수 표현 함수(웹·모바일 공용, ADR-011 §2.1 / ADR-055).
// `Intl`만 사용(플랫폼 무관). RN(Hermes)은 Expo SDK 56의 ICU-enabled Intl로 timeZone을 지원한다.
import type { TripDayHoliday, TripViewDay } from '@pinvi/schemas';

export function formatTripDate(value: string | null): string {
  if (!value) return '미정';
  // date-only ISO('YYYY-MM-DD', KST 민간일)는 UTC 자정으로 파싱되므로 UTC로 포맷해
  // 기기 timezone(UTC 서쪽)에서 하루 밀리는 표시를 막는다.
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(value));
}

/** ISO 시각 → 한국시(KST) `HH:MM`. rise/set 시각 표시용. 값 없으면 null. */
export function formatKstTime(value: string | null | undefined): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  }).format(new Date(value));
}

export function holidayLabel(holidays: TripDayHoliday[] | undefined): string | null {
  const names = Array.from(
    new Set((holidays ?? []).map((holiday) => holiday.name).filter(Boolean)),
  );
  if (names.length === 0) return null;
  return `공휴일 · ${names.join(', ')}`;
}

export function holidaysByDate(
  days: Pick<TripViewDay, 'date' | 'holidays'>[],
): Map<string, TripDayHoliday[]> {
  const map = new Map<string, TripDayHoliday[]>();
  for (const day of days) {
    if (!day.date || day.holidays.length === 0) continue;
    map.set(day.date, day.holidays);
  }
  return map;
}

export function formatTripDateWithHoliday(
  value: string | null,
  holidays?: TripDayHoliday[],
): string {
  const label = holidayLabel(holidays);
  return label ? `${formatTripDate(value)} (${label})` : formatTripDate(value);
}

export function formatTripDateRange(
  startDate: string | null,
  endDate: string | null,
  holidayMap?: Map<string, TripDayHoliday[]>,
): string {
  const start = formatTripDateWithHoliday(
    startDate,
    startDate ? holidayMap?.get(startDate) : undefined,
  );
  const end = formatTripDateWithHoliday(endDate, endDate ? holidayMap?.get(endDate) : undefined);
  return `${start} - ${end}`;
}
