import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TripDayHeader, type TripDayHeaderProps } from '@/components/trips/TripDayHeader';

function makeDay(over: Partial<TripDayHeaderProps['day']> = {}): TripDayHeaderProps['day'] {
  return {
    day_index: 1,
    date: null,
    effective_date: '2026-06-10',
    out_of_range: false,
    holidays: [],
    rise_set: null,
    rise_set_reference: null,
    ...over,
  };
}

describe('TripDayHeader', () => {
  it('effective_date를 표시한다', () => {
    render(<TripDayHeader day={makeDay()} />);
    expect(screen.getByTestId('trip-day-header')).toHaveTextContent('2026');
  });

  it('out_of_range면 경고 뱃지를 표시한다', () => {
    render(<TripDayHeader day={makeDay({ out_of_range: true })} />);
    expect(screen.getByTestId('trip-day-header-out-of-range')).toHaveTextContent('기간 벗어남');
  });

  it('공휴일을 뱃지로 표시한다', () => {
    render(
      <TripDayHeader
        day={makeDay({ holidays: [{ date: '2026-06-10', name: '광복절', dataset: 'holidays' }] })}
      />,
    );
    expect(screen.getByTestId('trip-day-header-holiday')).toHaveTextContent('광복절');
  });

  it('rise_set success면 일출/일몰 시각과 기준을 표시한다', () => {
    render(
      <TripDayHeader
        day={makeDay({
          rise_set: {
            status: 'success',
            locdate: '2026-06-10',
            sunrise_at: '2026-06-10T05:11:00+09:00',
            sunset_at: '2026-06-10T19:45:00+09:00',
            moonrise_at: null,
            moonset_at: null,
            fetched_at: '2026-06-09T00:00:00+09:00',
            updated_at: '2026-06-09T00:00:00+09:00',
          },
          rise_set_reference: '광안리 해수욕장',
        })}
      />,
    );
    const rs = screen.getByTestId('trip-day-rise-set');
    expect(rs).toHaveTextContent('일출 05:11');
    expect(rs).toHaveTextContent('일몰 19:45');
    expect(rs).toHaveTextContent('광안리 해수욕장 기준');
  });

  it('rise_set이 pending이면 준비 중 안내를 표시한다', () => {
    render(
      <TripDayHeader
        day={makeDay({
          rise_set: {
            status: 'pending_fetch',
            locdate: '2026-06-10',
            sunrise_at: null,
            sunset_at: null,
            moonrise_at: null,
            moonset_at: null,
            fetched_at: null,
            updated_at: '2026-06-09T00:00:00+09:00',
          },
        })}
      />,
    );
    expect(screen.getByTestId('trip-day-rise-set-pending')).toBeInTheDocument();
    expect(screen.queryByTestId('trip-day-rise-set')).not.toBeInTheDocument();
  });

  it('rise_set이 null이면 일출/일몰 행을 렌더하지 않는다', () => {
    render(<TripDayHeader day={makeDay({ rise_set: null })} />);
    expect(screen.queryByTestId('trip-day-rise-set')).not.toBeInTheDocument();
    expect(screen.queryByTestId('trip-day-rise-set-pending')).not.toBeInTheDocument();
  });

  it('rise_set이 failed면 "준비 중"으로 오인 표시하지 않는다', () => {
    render(
      <TripDayHeader
        day={makeDay({
          rise_set: {
            status: 'failed',
            locdate: '2026-06-10',
            sunrise_at: null,
            sunset_at: null,
            moonrise_at: null,
            moonset_at: null,
            fetched_at: '2026-06-09T00:00:00+09:00',
            updated_at: '2026-06-09T00:00:00+09:00',
          },
        })}
      />,
    );
    expect(screen.queryByTestId('trip-day-rise-set-pending')).not.toBeInTheDocument();
    expect(screen.queryByTestId('trip-day-rise-set')).not.toBeInTheDocument();
  });

  it('showSummary=false면 날짜/공휴일 요약 행을 숨기고 일출/일몰만 남긴다', () => {
    render(
      <TripDayHeader
        showSummary={false}
        day={makeDay({
          out_of_range: true,
          holidays: [{ date: '2026-06-10', name: '광복절', dataset: 'holidays' }],
        })}
      />,
    );
    expect(screen.queryByTestId('trip-day-header-out-of-range')).not.toBeInTheDocument();
    expect(screen.queryByTestId('trip-day-header-holiday')).not.toBeInTheDocument();
  });
});
