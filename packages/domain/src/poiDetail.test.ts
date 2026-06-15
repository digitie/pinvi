import { describe, expect, it } from 'vitest';
import { buildPoiDetailPatch, parseAmount, type PoiDetailForm } from './poiDetail';

describe('poiDetail', () => {
  it('parseAmount: 빈값/음수/비숫자 → null, 양수 → number', () => {
    expect(parseAmount('')).toBeNull();
    expect(parseAmount('  ')).toBeNull();
    expect(parseAmount('-5')).toBeNull();
    expect(parseAmount('abc')).toBeNull();
    expect(parseAmount('0')).toBe(0);
    expect(parseAmount('12000')).toBe(12000);
  });

  it('buildPoiDetailPatch: 폼 → PoiUpdate (빈 시각/금액 → null)', () => {
    const form: PoiDetailForm = {
      color: 'P-01',
      icon: 'restaurant',
      arrival: '',
      departure: '',
      budget: '15000',
      actual: '',
      note: '  맛집  ',
      url: 'https://example.com',
    };
    expect(buildPoiDetailPatch(form)).toEqual({
      custom_marker_color: 'P-01',
      custom_marker_icon: 'restaurant',
      planned_arrival_at: null,
      planned_departure_at: null,
      budget_amount: 15000,
      actual_amount: null,
      user_note: '맛집',
      user_url: 'https://example.com',
    });
  });

  it('buildPoiDetailPatch: 빈 icon → marker, 빈 note/url → null', () => {
    const form: PoiDetailForm = {
      color: 'P-13',
      icon: '  ',
      arrival: '',
      departure: '',
      budget: '',
      actual: '',
      note: '',
      url: '',
    };
    const patch = buildPoiDetailPatch(form);
    expect(patch.custom_marker_icon).toBe('marker');
    expect(patch.user_note).toBeNull();
    expect(patch.user_url).toBeNull();
  });
});
