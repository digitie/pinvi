import { describe, expect, it } from 'vitest';
import {
  MARKER_ICON_GLYPHS,
  MARKER_ICON_OPTIONS,
  makiIconName,
  makiIconUrl,
  markerGlyphName,
} from './markerIcons';
import { WEATHER_GLYPH_NAMES, WEATHER_TONES, weatherGlyphName } from './weatherNow';

describe('마커 아이콘 그림 이름(웹·모바일 공용)', () => {
  it('아이콘 고르기 목록의 모든 이름이 묶인 그림을 갖는다(외부 요청 없이 그린다)', () => {
    expect(MARKER_ICON_OPTIONS.filter((option) => markerGlyphName(option.icon) == null)).toEqual(
      [],
    );
    expect(Object.keys(MARKER_ICON_GLYPHS).sort()).toEqual(
      MARKER_ICON_OPTIONS.map((option) => option.icon).sort(),
    );
  });

  it('옛 별칭은 바꿔 찾고, 목록 밖 이름은 null — maki SVG 주소로 받는다', () => {
    expect(makiIconName('camera')).toBe('viewpoint');
    expect(markerGlyphName('camera')).toBe('Camera');
    expect(markerGlyphName('library')).toBeNull();
    expect(markerGlyphName('toString')).toBeNull();
    expect(makiIconUrl('library')).toBe('https://unpkg.com/@mapbox/maki@8.0.0/icons/library.svg');
  });
});

describe('날씨 그림 이름', () => {
  it('맑음·구름 조금만 밤 그림이 따로 있다', () => {
    expect(weatherGlyphName('clear')).toBe('Sun');
    expect(weatherGlyphName('clear', true)).toBe('Moon');
    expect(weatherGlyphName('partly', true)).toBe('CloudMoon');
    expect(weatherGlyphName('rain', true)).toBe('CloudRain');
    expect(weatherGlyphName('unknown')).toBe('Thermometer');
  });

  it('모든 상태가 그림·색 의미를 갖고, 그림 이름 목록은 중복이 없다', () => {
    for (const condition of Object.keys(WEATHER_TONES) as (keyof typeof WEATHER_TONES)[]) {
      expect(WEATHER_GLYPH_NAMES).toContain(weatherGlyphName(condition));
      expect(WEATHER_GLYPH_NAMES).toContain(weatherGlyphName(condition, true));
    }
    expect(new Set(WEATHER_GLYPH_NAMES).size).toBe(WEATHER_GLYPH_NAMES.length);
  });
});
