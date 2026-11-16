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

const WEEKDAY_LABELS = ['일', '월', '화', '수', '목', '금', '토'] as const;

export interface TripWeekday {
  /** '일'~'토'. */
  label: (typeof WEEKDAY_LABELS)[number];
  /** 0=일요일 … 6=토요일. */
  index: number;
}

/** date-only ISO('YYYY-MM-DD', KST 민간일)의 요일. `formatTripDate`와 같이 UTC로 읽어 기기 timezone과 무관하다. */
export function tripWeekday(value: string | null | undefined): TripWeekday | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  const index = parsed.getUTCDay();
  return { label: WEEKDAY_LABELS[index]!, index };
}

/** 날짜 + 요일 — 예: `2026년 11월 16일 (월)`. 날짜가 없으면 `미정`. */
export function formatTripDateWithWeekday(value: string | null): string {
  const weekday = tripWeekday(value);
  return weekday ? `${formatTripDate(value)} (${weekday.label})` : formatTripDate(value);
}

/** 달력 관례의 강조 — 일요일·공휴일은 'holiday', 토요일은 'saturday', 그 밖은 null. */
export function tripDayTone(
  value: string | null | undefined,
  holidays?: TripDayHoliday[],
): 'holiday' | 'saturday' | null {
  const weekday = tripWeekday(value);
  if ((holidays ?? []).some((holiday) => holiday.name) || weekday?.index === 0) return 'holiday';
  if (weekday?.index === 6) return 'saturday';
  return null;
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
