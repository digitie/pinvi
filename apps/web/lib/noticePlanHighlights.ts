/** 추천 여행 주변 정보(축제·큐레이션) 표시용 포맷터 — `components/notice-plans/NoticePlanHighlights.tsx`. */

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: 'short',
  day: 'numeric',
});

function formatDay(value: string): string {
  // date-only 값을 서울 자정으로 고정해 표시 시간대와 상관없이 같은 날짜가 나오게 한다.
  return dateFormatter.format(new Date(`${value}T00:00:00+09:00`));
}

export function formatEventPeriod(start: string | null, end: string | null): string {
  if (!start && !end) return '일정 미정';
  if (!start || !end || start === end) return formatDay((start ?? end) as string);
  return `${formatDay(start)} – ${formatDay(end)}`;
}

export function formatNearDistance(meters: number | null): string | null {
  if (meters == null) return null;
  if (meters < 1000) return `일정 장소에서 ${Math.round(meters)}m`;
  return `일정 장소에서 ${(meters / 1000).toFixed(1)}km`;
}
