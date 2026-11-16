// 일자 요일·공휴일(요청 17)과 장소 일출·일몰(요청 18) 표시.
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  PoiRiseSetLine,
  TripDayDateLabel,
  TripDayHeader,
  type TripDayHeaderProps,
} from '@/components/trips/TripDayHeader';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripViewPoiSchema } from '@pinvi/schemas';

const SUCCESS = {
  status: 'success' as const,
  locdate: '2026-06-10',
  sunrise_at: '2026-06-10T05:09:00+09:00',
  sunset_at: '2026-06-10T19:37:00+09:00',
  moonrise_at: null,
  moonset_at: null,
  fetched_at: null,
  updated_at: '2026-06-09T00:00:00+09:00',
};

function day(over: Partial<TripDayHeaderProps['day']> = {}): TripDayHeaderProps['day'] {
  return {
    day_index: 1,
    date: null,
    effective_date: '2026-11-16',
    out_of_range: false,
    holidays: [],
    rise_set: null,
    rise_set_reference: null,
    ...over,
  };
}

describe('일자 요일·공휴일 (요청 17)', () => {
  it('평일은 요일만 붙이고 강조하지 않는다', () => {
    render(<TripDayDateLabel value="2026-11-16" />);
    expect(screen.getByTestId('trip-day-date')).toHaveTextContent(/16일\s*\(월\)$/);
    expect(screen.getByTestId('trip-day-date')).not.toHaveAttribute('data-day-tone');
  });

  it('토요일은 saturday, 일요일은 holiday 톤', () => {
    const { rerender } = render(<TripDayDateLabel value="2026-11-21" />);
    expect(screen.getByTestId('trip-day-date')).toHaveAttribute('data-day-tone', 'saturday');
    expect(screen.getByTestId('trip-day-weekday')).toHaveTextContent('(토)');
    rerender(<TripDayDateLabel value="2026-11-22" />);
    expect(screen.getByTestId('trip-day-date')).toHaveAttribute('data-day-tone', 'holiday');
    expect(screen.getByTestId('trip-day-weekday')).toHaveClass('text-error-text');
  });

  it('평일 공휴일(KASI 특일)은 holiday 톤 + 이름 뱃지', () => {
    render(
      <TripDayHeader
        day={day({
          effective_date: '2026-10-09',
          holidays: [{ date: '2026-10-09', name: '한글날', dataset: 'holidays' }],
        })}
      />,
    );
    expect(screen.getByTestId('trip-day-date')).toHaveAttribute('data-day-tone', 'holiday');
    expect(screen.getByTestId('trip-day-weekday')).toHaveTextContent('(금)');
    expect(screen.getByTestId('trip-day-header-holiday')).toHaveTextContent('한글날');
  });

  it('날짜가 없으면 미정이고 요일이 없다', () => {
    render(<TripDayDateLabel value={null} />);
    expect(screen.getByTestId('trip-day-date')).toHaveTextContent('미정');
    expect(screen.queryByTestId('trip-day-weekday')).toBeNull();
  });
});

describe('장소 일출·일몰 (요청 18)', () => {
  it('success면 KST 일출·일몰을 보인다', () => {
    render(<PoiRiseSetLine riseSet={SUCCESS} />);
    const line = screen.getByTestId('trip-poi-rise-set');
    expect(line).toHaveTextContent('일출 05:09');
    expect(line).toHaveTextContent('일몰 19:37');
  });

  it('계산되지 않은 상태는 아무것도 보이지 않는다', () => {
    const { container } = render(
      <PoiRiseSetLine
        riseSet={{ ...SUCCESS, status: 'pending_coord', sunrise_at: null, sunset_at: null }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('장소 목록은 날씨를 보일 때 장소 날씨 아래에 일출·일몰을 보인다', () => {
    const poi = TripViewPoiSchema.parse({
      poi_id: '00000000-0000-4000-8000-000000000001',
      feature_id: null,
      sort_order: 'a0',
      title: '광안리',
      feature: {},
      marker_color: null,
      marker_icon: null,
      feature_resolution_state: 'not_linked',
      user_note: null,
      planned_arrival_at: null,
      planned_departure_at: null,
      budget_amount: null,
      actual_amount: null,
      currency: 'KRW',
      user_url: null,
      rise_set: SUCCESS,
      feature_link_broken_at: null,
      version: 1,
      created_at: '2026-11-03T00:00:00Z',
      updated_at: '2026-11-03T00:00:00Z',
    });
    const { rerender } = render(<TripPoiList pois={[poi]} dayDate="2026-06-10" showWeather />);
    expect(screen.getByTestId('trip-poi-rise-set')).toHaveTextContent('일출 05:09');
    rerender(<TripPoiList pois={[poi]} dayDate="2026-06-10" />);
    expect(screen.queryByTestId('trip-poi-rise-set')).toBeNull();
  });
});
