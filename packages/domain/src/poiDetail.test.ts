import { describe, expect, it } from 'vitest';
import {
  buildPoiDetailPatch,
  parseAmount,
  validateAmountInput,
  type PoiDetailForm,
} from './poiDetail';

describe('poiDetail', () => {
  it('validateAmountInput: 빈값 → ok null, 0 이상 십진수 → ok value', () => {
    expect(validateAmountInput('')).toEqual({ ok: true, value: null });
    expect(validateAmountInput('  ')).toEqual({ ok: true, value: null });
    expect(validateAmountInput('0')).toEqual({ ok: true, value: 0 });
    expect(validateAmountInput(' 30000 ')).toEqual({ ok: true, value: 30000 });
    expect(validateAmountInput('12.5')).toEqual({ ok: true, value: 12.5 });
  });

  it('validateAmountInput: 음수/비숫자/지수/부호/쉼표는 사용자 메시지로 거부', () => {
    for (const raw of ['-5', 'abc', '1e3', '+10', '30,000', '1.', '.5', 'Infinity', 'NaN']) {
      const result = validateAmountInput(raw);
      expect(result.ok, raw).toBe(false);
      if (!result.ok) expect(result.message).toContain('0 이상의 숫자');
    }
  });

  it('validateAmountInput: safe integer 초과는 거부', () => {
    const result = validateAmountInput('9007199254740993');
    expect(result.ok).toBe(false);
  });

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
