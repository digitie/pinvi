import { poiApi } from '@pinvi/api-client';
import { createPoiWeatherStore, type PoiWeatherLoader } from '@pinvi/hooks';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { apiClient } from './api';

/**
 * 장소별 현재 날씨 카드(`GET /trips/{id}/pois/{poi}/weather`) 공유 캐시 — 모바일 인스턴스.
 * 규칙(동시 2건, 10분 신선·1분 재시도, 구독자 없으면 큐에서 뺌, 지도 마커는 요청 없이 읽기)은 웹과 같은
 * `@pinvi/hooks` `createPoiWeatherStore`다.
 */
const loadPoiWeather: PoiWeatherLoader<FeatureWeatherCard> = (tripId, poiId) =>
  poiApi(apiClient).weather(tripId, poiId);

export const poiWeatherStore = createPoiWeatherStore(loadPoiWeather);
export const { usePoiWeather, usePoiWeatherPeekAll, refreshPoiWeather } = poiWeatherStore;
