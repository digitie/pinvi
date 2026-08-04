import { describe, expect, it } from 'vitest';
import { formatKstTime, formatTripDate, formatTripDateRange, holidayLabel } from './tripDateLabels';

describe('formatTripDate', () => {
  it('null이면 미정', () => {
    expect(formatTripDate(null)).toBe('미정');
  });
  it('ISO 날짜를 ko-KR로 포맷', () => {
    // 로케일 데이터 의존을 줄이려 연/일 숫자와 월 존재만 확인.
    const out = formatTripDate('2026-07-01');
    expect(out).toContain('2026');
    expect(out).toContain('1');
  });
});

describe('formatKstTime', () => {
  it('값 없으면 null', () => {
    expect(formatKstTime(null)).toBeNull();
    expect(formatKstTime(undefined)).toBeNull();
  });
  it('UTC ISO 시각을 KST HH:MM로(Asia/Seoul, +9h)', () => {
    // 2026-07-01T00:00:00Z → KST 09:00.
    expect(formatKstTime('2026-07-01T00:00:00Z')).toBe('09:00');
  });
});

describe('holidayLabel', () => {
  it('빈 목록이면 null', () => {
    expect(holidayLabel([])).toBeNull();
    expect(holidayLabel(undefined)).toBeNull();
  });
  it('중복 제거 + 공휴일 접두', () => {
    expect(
      holidayLabel([
        { date: '2026-07-01', name: '제헌절' },
        { date: '2026-07-01', name: '제헌절' },
      ] as never),
    ).toBe('공휴일 · 제헌절');
  });
});

describe('formatTripDateRange', () => {
  it('시작-끝 결합', () => {
    const out = formatTripDateRange('2026-07-01', '2026-07-03');
    expect(out).toContain(' - ');
  });
});
