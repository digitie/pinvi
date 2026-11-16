'use client';

import { weatherIconFor, WEATHER_TONE } from '@/lib/weatherIcons';
import type { WeatherConditionKind } from '@/lib/weatherNow';
import { createElement } from 'react';

export interface WeatherIconProps {
  condition: WeatherConditionKind;
  night?: boolean;
  className?: string;
  /** 생략하면 장식(aria-hidden)으로 렌더한다. */
  label?: string;
}

/** 날씨 상태 아이콘. 지도 마커 라벨 등 다른 화면도 이 컴포넌트·매핑을 재사용한다. */
export function WeatherIcon({
  condition,
  night = false,
  className = 'h-4 w-4',
  label,
}: WeatherIconProps) {
  // 아이콘 컴포넌트는 정적 매핑에서 고른다(렌더 중 새 컴포넌트를 만들지 않는다) — createElement로 그린다.
  const props = {
    className: `${className} shrink-0 ${WEATHER_TONE[condition]}`,
    'aria-hidden': label ? undefined : true,
    'aria-label': label,
    role: label ? 'img' : undefined,
    'data-weather-condition': condition,
  };
  return createElement(
    weatherIconFor(condition, night),
    props,
    label ? <title>{label}</title> : null,
  );
}
