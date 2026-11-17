'use client';

import { WeatherIcon } from '@/components/weather/WeatherIcon';
import { placeCurrentWeather } from '@pinvi/domain';
import { useMinuteNow, usePoiWeatherPeek } from '@/lib/usePoiWeather';
import { conditionLabel, formatTemp } from '@pinvi/domain';
import type { TripWeatherCard } from '@pinvi/schemas';
import { useMemo } from 'react';

export interface PlaceWeatherSource {
  /** 장소별 현재 날씨 공유 캐시 키(목록 배지가 받은 카드). 공유 화면처럼 없으면 일자 카드만 쓴다. */
  tripId?: string | null;
  poiId: string;
  /** 여행 화면이 이미 받은 일자 날씨 카드. */
  dayCard?: TripWeatherCard | null;
}

/** 마커 라벨용 현재 날씨 — 새 요청 없이 이미 받은 카드에서(`lib/placeWeather`). */
export function usePlaceWeather({ tripId, poiId, dayCard }: PlaceWeatherSource) {
  const poiCard = usePoiWeatherPeek(tripId, poiId);
  const now = useMinuteNow();
  return useMemo(
    () => (now === 0 ? null : placeCurrentWeather(poiCard, dayCard, now)),
    [poiCard, dayCard, now],
  );
}

/**
 * 장소 마커 이름 옆의 작은 현재 날씨 아이콘. 아이콘·색은 장소 목록 배지와 같은 `WeatherIcon`이다.
 * 지도 바탕 위에서도 읽히게 흰 halo를 두른다. 날씨를 모르면 아무것도 그리지 않는다.
 */
export function PlaceWeatherGlyph({
  source,
  decorative = false,
}: {
  source: PlaceWeatherSource;
  /** 이미 이름을 가진 컨트롤(마커 버튼) 안이면 true — 읽기 순서를 어지럽히지 않게 숨긴다. */
  decorative?: boolean;
}) {
  const weather = usePlaceWeather(source);
  if (!weather) return null;
  const label = [conditionLabel(weather.condition), weather.temp != null ? formatTemp(weather.temp) : null]
    .filter(Boolean)
    .join(' ');
  return (
    <span
      className="inline-flex shrink-0 items-center"
      data-testid="place-weather-glyph"
      data-weather-kind={weather.condition}
      title={label}
      style={{ filter: 'drop-shadow(0 0 1px #fff) drop-shadow(0 0 1px #fff)' }}
      {...(decorative ? { 'aria-hidden': true } : {})}
    >
      <WeatherIcon
        condition={weather.condition}
        night={weather.night}
        className="h-3.5 w-3.5"
        label={decorative ? undefined : `날씨 ${label}`}
      />
    </span>
  );
}
