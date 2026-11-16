'use client';

import { CONDITION_LABELS, type WeatherConditionKind } from '@/lib/weatherNow';
import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudHail,
  CloudLightning,
  CloudMoon,
  CloudRain,
  CloudSnow,
  CloudSun,
  Cloudy,
  Moon,
  Sun,
  Thermometer,
  type LucideIcon,
} from 'lucide-react';

const DAY_ICONS: Record<WeatherConditionKind, LucideIcon> = {
  clear: Sun,
  partly: CloudSun,
  cloudy: Cloud,
  overcast: Cloudy,
  rain: CloudRain,
  shower: CloudDrizzle,
  sleet: CloudHail,
  snow: CloudSnow,
  thunder: CloudLightning,
  fog: CloudFog,
  unknown: Thermometer,
};

/** 해·구름이 섞인 상태만 밤 아이콘이 따로 있다. */
const NIGHT_ICONS: Partial<Record<WeatherConditionKind, LucideIcon>> = {
  clear: Moon,
  partly: CloudMoon,
};

/** 상태별 색 — 맑음은 주황, 강수는 파랑, 그 밖은 본문색. 토큰 class만 쓴다. */
const TONE: Record<WeatherConditionKind, string> = {
  clear: 'text-warning-text',
  partly: 'text-warning-text',
  cloudy: 'text-muted',
  overcast: 'text-muted',
  rain: 'text-primary',
  shower: 'text-primary',
  sleet: 'text-primary',
  snow: 'text-primary',
  thunder: 'text-error-text',
  fog: 'text-muted',
  unknown: 'text-muted',
};

export function weatherIconFor(condition: WeatherConditionKind, night = false): LucideIcon {
  return (night ? NIGHT_ICONS[condition] : undefined) ?? DAY_ICONS[condition];
}

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
  const Icon = weatherIconFor(condition, night);
  return (
    <Icon
      className={`${className} shrink-0 ${TONE[condition]}`}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
      data-weather-condition={condition}
    >
      {label ? <title>{label}</title> : null}
    </Icon>
  );
}

export function conditionLabel(condition: WeatherConditionKind): string {
  return CONDITION_LABELS[condition];
}
