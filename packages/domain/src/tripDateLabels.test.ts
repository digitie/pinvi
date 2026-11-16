import { describe, expect, it } from 'vitest';
import {
  formatKstTime,
  formatTripDate,
  formatTripDateRange,
  formatTripDateWithWeekday,
  holidayLabel,
  tripDayTone,
  tripWeekday,
} from './tripDateLabels';

describe('formatTripDate', () => {
  it('null이면 미정', () => {
    expect(formatTripDate(null)).toBe('미정');
  });
  it('ISO 날짜를 ko-KR로 포맷 (UTC 고정 — 기기 timezone 무관)', () => {
    // date-only는 UTC 자정 파싱 + timeZone:'UTC' 포맷이라 러너/기기 timezone에 무관하게
    // 같은 민간일이 나온다(서쪽 timezone에서 하루 밀림 방지).
    const out = formatTripDate('2026-07-01');
    expect(out).toContain('2026');
    expect(out).toContain('7');
    expect(out).toMatch(/1\.?\s*$|1일/);
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

describe('요일·공휴일 강조 (요청 17)', () => {
  it('date-only 날짜의 요일을 기기 timezone과 무관하게 낸다', () => {
    expect(tripWeekday('2026-11-16')).toEqual({ label: '월', index: 1 });
    expect(tripWeekday('2026-11-15')).toEqual({ label: '일', index: 0 });
    expect(tripWeekday('2026-11-21')).toEqual({ label: '토', index: 6 });
    expect(tripWeekday(null)).toBeNull();
    expect(tripWeekday('not-a-date')).toBeNull();
  });
  it('날짜 뒤에 요일을 괄호로 붙인다', () => {
    expect(formatTripDateWithWeekday('2026-11-16')).toMatch(/16일 \(월\)$/);
    expect(formatTripDateWithWeekday(null)).toBe('미정');
  });
  it('일요일·공휴일은 holiday, 토요일은 saturday', () => {
    expect(tripDayTone('2026-11-15')).toBe('holiday');
    expect(tripDayTone('2026-11-21')).toBe('saturday');
    expect(tripDayTone('2026-11-16')).toBeNull();
    expect(
      tripDayTone('2026-11-16', [{ date: '2026-11-16', name: '대체공휴일', dataset: 'holidays' }]),
    ).toBe('holiday');
    expect(tripDayTone(null)).toBeNull();
  });
});
