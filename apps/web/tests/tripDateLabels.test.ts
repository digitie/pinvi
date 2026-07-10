import { describe, expect, it } from 'vitest';
import { formatTripDateRange, holidayLabel, holidaysByDate } from '@/lib/tripDateLabels';

describe('tripDateLabels', () => {
  it('공휴일 이름을 중복 없이 날짜 라벨에 붙인다', () => {
    const holidays = [
      { date: '2026-08-15', name: '광복절', dataset: 'holidays' as const },
      { date: '2026-08-15', name: '광복절', dataset: 'national_holidays' as const },
    ];

    expect(holidayLabel(holidays)).toBe('공휴일 · 광복절');
  });

  it('여행 일자 공휴일을 기간 표시 양 끝 날짜에 반영한다', () => {
    const holidayMap = holidaysByDate([
      {
        date: '2026-08-15',
        holidays: [{ date: '2026-08-15', name: '광복절', dataset: 'holidays' }],
      },
    ]);

    expect(formatTripDateRange('2026-08-15', '2026-08-16', holidayMap)).toContain(
      '공휴일 · 광복절',
    );
  });
});
