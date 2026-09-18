/**
 * 날씨 provider 원문 키 → 국문 표시 라벨 (ADR-068, T-366/T-368 공용).
 *
 * `TripWeatherSummary`(여행 상세 카드)와 `FeatureMapView`(지도 weather marker) 둘 다
 * 값의 출처(provider)를 사용자에게 보여준다 — 같은 provider가 두 표면에서 다르게
 * 보이면 안 되므로 여기 하나로 둔다.
 */
const PROVIDER_LABELS: Record<string, string> = {
  'python-kma-api': '기상청',
  'python-airkorea-api': '환경공단',
  'python-khoa-api': '국립해양조사원',
  'python-krforest-api': '산림청',
  'python-krex-api': '한국도로공사',
  openweathermap: 'OpenWeatherMap',
  weatherapi: 'WeatherAPI',
  open_meteo: 'Open-Meteo',
  wttr_in: 'wttr.in',
};

export function providerLabel(provider: string | null | undefined): string | null {
  if (!provider) return null;
  return PROVIDER_LABELS[provider] ?? provider;
}
