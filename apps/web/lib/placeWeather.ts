/**
 * 지도 마커 이름 옆 "장소의 현재 날씨" 아이콘의 데이터.
 *
 * 새 요청을 만들지 않는다. 두 곳에서 이미 받은 값을 쓴다.
 *  1. 장소 목록 배지·날씨 팝업이 받은 장소별 현재 날씨 카드(`usePoiWeather` 공유 캐시) — 있으면 우선.
 *  2. 여행 화면이 받은 일자별 날씨 카드(`day.weather_cards` + `day.weather_by_feature_id`).
 * 상태 판정·아이콘은 장소 목록 배지와 같은 규칙(`lib/weatherNow.currentWeather`, `WeatherIcon`)이다 —
 * 같은 장소가 목록과 지도에서 다른 날씨로 보이지 않게.
 */

import { currentWeather, type CurrentWeather } from '@/lib/weatherNow';
import type { FeatureWeatherCard, TripViewDay, TripWeatherCard } from '@pinvi/schemas';

/** 여행의 모든 일자에서 POI별 일자 날씨 카드(카드가 없는 장소는 뺀다). */
export function placeWeatherCards(days: readonly TripViewDay[]): Record<string, TripWeatherCard> {
  const result: Record<string, TripWeatherCard> = {};
  for (const day of days) {
    for (const poi of day.pois) {
      if (!poi.feature_id) continue;
      const resolution = day.weather_by_feature_id[poi.feature_id];
      if (resolution?.state !== 'found') continue;
      const card = day.weather_cards[resolution.card_key];
      if (card && card.metrics.length > 0) result[poi.poi_id] = card;
    }
  }
  return result;
}

/**
 * 마커에 붙일 현재 날씨. 장소 현재 카드가 있으면 그것, 없으면 일자 카드로 판정한다. 상태를 모르면
 * null(아이콘을 그리지 않는다 — 값을 지어내지 않는다).
 */
export function placeCurrentWeather(
  poiCard: FeatureWeatherCard | null | undefined,
  dayCard: TripWeatherCard | null | undefined,
  now: number,
): CurrentWeather | null {
  const card: FeatureWeatherCard | null =
    poiCard ?? (dayCard ? { feature_id: 'trip-day', ...dayCard } : null);
  const weather = currentWeather(card, now);
  return weather && weather.condition !== 'unknown' ? weather : null;
}
