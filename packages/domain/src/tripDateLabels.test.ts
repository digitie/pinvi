import { describe, expect, it } from 'vitest';
import { formatKstTime, formatTripDate, formatTripDateRange, holidayLabel } from './tripDateLabels';

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
