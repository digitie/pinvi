// 예보 범위 밖 날짜 안내(2026-11-17 소유자 승인 결정 3). 범위는 서버가 받은 예보의 마지막 날짜
// (`TripWeatherResolution.no_data.forecast_until`)에서 온다 — 고정 일수를 박지 않는다.

const KST_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** 지금의 KST 날짜(`YYYY-MM-DD`). */
export function kstToday(now: Date = new Date()): string {
  return KST_DATE.format(now);
}

function dayNumber(isoDate: string): number {
  return Math.round(Date.parse(`${isoDate}T00:00:00Z`) / 86_400_000);
}

/** `date`가 예보 범위(`forecastUntil`까지) 밖인지. 범위를 모르면 false. */
export function isBeyondForecast(
  date: string | null | undefined,
  forecastUntil: string | null | undefined,
): boolean {
  return Boolean(date && forecastUntil && date > forecastUntil);
}

/** 예: `예보는 9일 앞(11월 26일)까지만 제공됩니다.` — N = 예보 마지막 날짜 − 오늘(KST). */
export function forecastHorizonMessage(forecastUntil: string, today: string = kstToday()): string {
  const days = dayNumber(forecastUntil) - dayNumber(today);
  const [, month, day] = forecastUntil.split('-').map(Number);
  if (days <= 0) return '예보는 오늘까지만 제공됩니다.';
  return `예보는 ${days}일 앞(${month}월 ${day}일)까지만 제공됩니다.`;
}
