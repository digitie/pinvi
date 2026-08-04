// Trip 날짜/공휴일/시각 라벨은 웹·모바일 공용이라 `@pinvi/domain`으로 이관했다(ADR-011 §2.1 / ADR-055).
// 웹 호출부(`@/lib/tripDateLabels`) 호환을 위해 재노출한다.
export {
  formatTripDate,
  formatKstTime,
  holidayLabel,
  holidaysByDate,
  formatTripDateWithHoliday,
  formatTripDateRange,
} from '@pinvi/domain';
