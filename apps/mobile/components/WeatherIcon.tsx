import { colors } from '@pinvi/design-tokens';
import {
  WEATHER_TONES,
  weatherGlyphName,
  type WeatherConditionKind,
  type WeatherTone,
} from '@pinvi/domain';
import { Glyph } from './Glyph';

/**
 * 색 의미(`WEATHER_TONES`) → hex. 웹은 같은 의미를 토큰 class로 그린다. warning은 공통 토큰
 * `--kt-warning`(oklch 50.9% 0.103 71)의 sRGB 값이다(RN은 oklch를 읽지 못한다).
 */
const TONE_HEX: Record<WeatherTone, string> = {
  warning: '#8a5a11',
  primary: colors.primary,
  error: colors['error-text'],
  muted: colors.muted,
};

/** 날씨 상태 아이콘(웹 `WeatherIcon` 대응 — 같은 상태는 같은 그림·색 의미). */
export function WeatherIcon({
  condition,
  night = false,
  size = 14,
}: {
  condition: WeatherConditionKind;
  night?: boolean;
  size?: number;
}) {
  return (
    <Glyph
      name={weatherGlyphName(condition, night)}
      size={size}
      color={TONE_HEX[WEATHER_TONES[condition]]}
      strokeWidth={2}
    />
  );
}
