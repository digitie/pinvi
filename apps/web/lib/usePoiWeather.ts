'use client';

/**
 * 장소별 현재 날씨 카드 공유 캐시 — 웹 인스턴스. 규칙(동시 2건, 10분 신선·1분 재시도, 구독자 없으면 큐에서
 * 뺌, 마커는 요청 없이 읽기)은 `@pinvi/hooks` `createPoiWeatherStore`가 정본이다(모바일과 공용).
 */
import { poiApi } from '@pinvi/api-client';
import {
  __resetMinuteNowForTest,
  createPoiWeatherStore,
  useMinuteNow,
  type PoiWeatherLoader,
  type PoiWeatherState as SharedPoiWeatherState,
} from '@pinvi/hooks';
import type { FeatureWeatherCard } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

export type PoiWeatherState = SharedPoiWeatherState<FeatureWeatherCard>;

const defaultLoader: PoiWeatherLoader<FeatureWeatherCard> = (tripId, poiId) =>
  poiApi(apiClient).weather(tripId, poiId);

const store = createPoiWeatherStore(defaultLoader);

export const usePoiWeather = store.usePoiWeather;
export const usePoiWeatherPeek = store.usePoiWeatherPeek;
export const refreshPoiWeather = store.refreshPoiWeather;
export { useMinuteNow };

/** 테스트 전용 — 캐시를 비우고 loader를 바꾼다. */
export function __resetPoiWeatherForTest(next?: PoiWeatherLoader<FeatureWeatherCard>): void {
  store.reset(next);
  __resetMinuteNowForTest();
}
