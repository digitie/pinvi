// 예보 범위 밖 날짜 전용 안내(2026-11-17 소유자 승인 결정 3).
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';
import { forecastHorizonMessage, isBeyondForecast, kstToday } from '@/lib/forecastHorizon';

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

describe('forecastHorizonMessage', () => {
  it('N은 예보 마지막 날짜 − 오늘(KST)이고 날짜를 함께 보인다', () => {
    expect(forecastHorizonMessage('2026-11-26', '2026-11-17')).toBe(
      '예보는 9일 앞(11월 26일)까지만 제공됩니다.',
    );
    expect(forecastHorizonMessage('2026-12-01', '2026-11-27')).toBe(
      '예보는 4일 앞(12월 1일)까지만 제공됩니다.',
    );
    expect(forecastHorizonMessage('2026-11-17', '2026-11-17')).toBe(
      '예보는 오늘까지만 제공됩니다.',
    );
  });

  it('범위 밖 판정은 날짜와 범위를 모두 알 때만', () => {
    expect(isBeyondForecast('2026-12-20', '2026-11-26')).toBe(true);
    expect(isBeyondForecast('2026-11-26', '2026-11-26')).toBe(false);
    expect(isBeyondForecast('2026-12-20', null)).toBe(false);
    expect(isBeyondForecast(null, '2026-11-26')).toBe(false);
  });

  it('KST 오늘은 UTC 15시에 넘어간다', () => {
    expect(kstToday(new Date('2026-11-16T14:59:00Z'))).toBe('2026-11-16');
    expect(kstToday(new Date('2026-11-16T15:00:00Z'))).toBe('2026-11-17');
  });
});

describe('예보 범위 밖 안내', () => {
  const today = kstToday();
  const until = addDays(today, 9);

  it('범위 밖 날짜는 전용 안내만, 새로고침 버튼은 없다', () => {
    render(
      <TripWeatherSummary
        weather={{ state: 'no_data', forecast_until: until }}
        date={addDays(today, 30)}
        onRefresh={vi.fn()}
      />,
    );
    const status = screen.getByTestId('trip-weather-status');
    expect(status).toHaveAttribute('data-weather-reason', 'beyond_forecast');
    expect(status).toHaveTextContent('예보는 9일 앞(');
    expect(status).not.toHaveTextContent('이 날짜의 날씨 정보가 없습니다.');
    expect(screen.queryByRole('button', { name: '날씨 새로고침' })).toBeNull();
  });

  it('범위 안이거나 범위를 모르면 기존 문구와 새로고침', () => {
    const { rerender } = render(
      <TripWeatherSummary
        weather={{ state: 'no_data', forecast_until: until }}
        date={addDays(today, 3)}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByTestId('trip-weather-status')).toHaveTextContent(
      '이 날짜의 날씨 정보가 없습니다.',
    );
    expect(screen.getByRole('button', { name: '날씨 새로고침' })).toBeInTheDocument();
    rerender(
      <TripWeatherSummary
        weather={{ state: 'no_data' }}
        date={addDays(today, 30)}
        onRefresh={vi.fn()}
      />,
    );
    expect(screen.getByTestId('trip-weather-status')).not.toHaveAttribute('data-weather-reason');
    expect(screen.getByRole('button', { name: '날씨 새로고침' })).toBeInTheDocument();
  });
});
