/**
 * 날씨 상태 → lucide 아이콘·색. 어떤 상태를 어떤 그림·색 의미로 그릴지는 `@pinvi/domain`
 * (`weatherGlyphName`, `WEATHER_TONES`)이 정본이다 — 모바일과 같은 날씨가 같은 그림으로 보인다.
 */
import {
  WEATHER_TONES,
  weatherGlyphName,
  type WeatherConditionKind,
  type WeatherGlyphName,
  type WeatherTone,
} from '@pinvi/domain';
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

const GLYPHS: Record<WeatherGlyphName, LucideIcon> = {
  Sun,
  CloudSun,
  Cloud,
  Cloudy,
  CloudRain,
  CloudDrizzle,
  CloudHail,
  CloudSnow,
  CloudLightning,
  CloudFog,
  Thermometer,
  Moon,
  CloudMoon,
};

const TONE_CLASS: Record<WeatherTone, string> = {
  warning: 'text-warning-text',
  primary: 'text-primary',
  error: 'text-error-text',
  muted: 'text-muted',
};

/** 상태별 색 class(토큰 class만 쓴다). */
export const WEATHER_TONE: Record<WeatherConditionKind, string> = Object.fromEntries(
  Object.entries(WEATHER_TONES).map(([condition, tone]) => [condition, TONE_CLASS[tone]]),
) as Record<WeatherConditionKind, string>;

export function weatherIconFor(condition: WeatherConditionKind, night = false): LucideIcon {
  return GLYPHS[weatherGlyphName(condition, night)];
}
