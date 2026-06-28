import { describe, expect, it } from 'vitest';
import {
  CATEGORY_MARKER,
  MARKER_PALETTE,
  markerStyleFor,
  paletteHex,
  paletteLabelColor,
  resolveMarkerStyle,
} from './marker';

describe('markerPalette', () => {
  it('16색이 모두 P-01~P-16 형식 + hex', () => {
    const keys = Object.keys(MARKER_PALETTE);
    expect(keys).toHaveLength(16);
    for (const key of keys) {
      expect(key).toMatch(/^P-\d{2}$/);
      expect(MARKER_PALETTE[key as keyof typeof MARKER_PALETTE].hex).toMatch(/^#[0-9A-F]{6}$/);
    }
  });

  it('paletteHex: 유효 코드 → hex, 미상/누락 → 회색(P-13)', () => {
    expect(paletteHex('P-01')).toBe('#E53935');
    expect(paletteHex('P-16')).toBe('#039BE5');
    expect(paletteHex('P-99')).toBe('#757575');
    expect(paletteHex(null)).toBe('#757575');
    expect(paletteHex(undefined)).toBe('#757575');
  });

  it('paletteLabelColor: 노랑(P-03)만 어두운 글자', () => {
    expect(paletteLabelColor('P-03')).toBe('#222222');
    expect(paletteLabelColor('P-01')).toBe('#FFFFFF');
    expect(paletteLabelColor('bogus')).toBe('#FFFFFF');
  });

  it('markerStyleFor: 카테고리 우선 → kind fallback → marker', () => {
    expect(markerStyleFor('음식점', 'place')).toEqual({ icon: 'restaurant', color: 'P-01' });
    expect(markerStyleFor('축제', 'place')).toEqual({ icon: 'star', color: 'P-11' });
    expect(markerStyleFor('공지', 'place')).toEqual({ icon: 'alert', color: 'P-14' });
    expect(markerStyleFor(null, 'event')).toEqual({ icon: 'star', color: 'P-11' });
    expect(markerStyleFor('미지의카테고리', 'notice')).toEqual({ icon: 'alert', color: 'P-14' });
    expect(markerStyleFor(null, null)).toEqual({ icon: 'marker', color: 'P-13' });
  });

  it('resolveMarkerStyle: custom → resolved → upstream → snapshot → category → kind 순서', () => {
    expect(
      resolveMarkerStyle({
        customColor: 'P-10',
        customIcon: 'lodging',
        resolvedColor: 'P-07',
        resolvedIcon: 'swimming',
        snapshot: { marker_color: 'P-03', marker_icon: 'monument', category: '국가유산' },
      }),
    ).toMatchObject({ color: 'P-10', icon: 'lodging', source: 'custom' });

    expect(
      resolveMarkerStyle({
        resolvedColor: 'P-07',
        resolvedIcon: 'swimming',
        snapshot: { marker_color: 'P-03', marker_icon: 'monument', category: '국가유산' },
      }),
    ).toMatchObject({ color: 'P-07', icon: 'swimming', source: 'resolved' });

    expect(
      resolveMarkerStyle({
        upstreamColor: 'P-02',
        upstreamIcon: 'fuel',
        upstreamCategory: '주유소',
        upstreamKind: 'price',
      }),
    ).toMatchObject({ color: 'P-02', icon: 'fuel', source: 'upstream' });

    expect(
      resolveMarkerStyle({
        snapshot: { marker_color: 'P-03', marker_icon: 'monument', category: '국가유산' },
      }),
    ).toMatchObject({ color: 'P-03', icon: 'monument', source: 'snapshot' });

    expect(resolveMarkerStyle({ upstreamCategory: '해수욕장' })).toMatchObject({
      color: 'P-07',
      icon: 'swimming',
      source: 'category',
    });
    expect(resolveMarkerStyle({ upstreamKind: 'notice' })).toMatchObject({
      color: 'P-14',
      icon: 'alert',
      source: 'kind',
    });
  });

  it('CATEGORY_MARKER 색상은 전부 팔레트에 존재', () => {
    for (const style of Object.values(CATEGORY_MARKER)) {
      expect(MARKER_PALETTE[style.color]).toBeDefined();
    }
  });
});
