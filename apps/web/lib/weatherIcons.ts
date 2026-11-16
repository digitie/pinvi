/**
 * 날씨 상태 → lucide 아이콘·색 매핑. `WeatherIcon` 컴포넌트와 지도 마커 라벨 등 다른 화면이 같은 매핑을
 * 쓴다(같은 날씨가 화면마다 다른 아이콘으로 보이지 않게).
 */
import type { WeatherConditionKind } from '@/lib/weatherNow';
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
export const WEATHER_TONE: Record<WeatherConditionKind, string> = {
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
