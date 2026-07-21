import type { TripDayHoliday, TripViewDay } from '@pinvi/schemas';

export function formatTripDate(value: string | null): string {
  if (!value) return '미정';
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
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
  const names = Array.from(new Set((holidays ?? []).map((holiday) => holiday.name).filter(Boolean)));
  if (names.length === 0) return null;
  return `공휴일 · ${names.join(', ')}`;
}

export function holidaysByDate(days: Pick<TripViewDay, 'date' | 'holidays'>[]): Map<string, TripDayHoliday[]> {
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
