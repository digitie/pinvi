// 날씨 새로고침 버튼(2026-11-16 소유자 요청 15).
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';
import { weatherRefreshMessage } from '@/lib/weatherRefreshMessage';
import type { TripWeatherRefreshResponse } from '@pinvi/schemas';

const BASE: TripWeatherRefreshResponse = {
  trip_id: '00000000-0000-4000-8000-000000000001',
  day_index: 1,
  refreshed: 0,
  cooldown: 0,
  no_data: 0,
  failed: 0,
  skipped: 0,
  retry_after_seconds: null,
};

describe('날씨 새로고침 버튼', () => {
  it('"이 날짜의 날씨 정보가 없습니다." 옆에 버튼이 있고, 누르면 결과를 안내한다', async () => {
    const onRefresh = vi.fn().mockResolvedValue({ ...BASE, refreshed: 1 });
    render(
      <TripWeatherSummary weather={{ state: 'no_data' }} date="2026-12-20" onRefresh={onRefresh} />,
    );
    const status = screen.getByTestId('trip-weather-status');
    expect(status).toHaveTextContent('이 날짜의 날씨 정보가 없습니다.');
    const button = screen.getByRole('button', { name: '날씨 새로고침' });
    expect(button.previousElementSibling).toHaveTextContent('이 날짜의 날씨 정보가 없습니다.');
    await act(async () => {
      fireEvent.click(button);
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('trip-weather-refresh-message')).toHaveTextContent(
      '날씨를 다시 확인했습니다.',
    );
  });

  it('누르는 동안은 다시 누를 수 없다', async () => {
    let resolve!: (value: TripWeatherRefreshResponse) => void;
    const onRefresh = vi.fn(() => new Promise<TripWeatherRefreshResponse>((r) => (resolve = r)));
    render(
      <TripWeatherSummary
        weather={{ state: 'unavailable' }}
        date="2026-12-20"
        onRefresh={onRefresh}
      />,
    );
    const button = screen.getByRole('button', { name: '날씨 새로고침' });
    fireEvent.click(button);
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    await act(async () => resolve({ ...BASE, cooldown: 1, retry_after_seconds: 42 }));
    expect(button).not.toBeDisabled();
    expect(screen.getByTestId('trip-weather-refresh-message')).toHaveTextContent('42초 뒤');
  });

  it('실패하면 다시 시도하라고 안내한다', async () => {
    const onRefresh = vi.fn().mockRejectedValue(new Error('429'));
    render(
      <TripWeatherSummary weather={{ state: 'no_data' }} date="2026-12-20" onRefresh={onRefresh} />,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '날씨 새로고침' }));
    });
    expect(screen.getByTestId('trip-weather-refresh-message')).toHaveTextContent(
      '새로 고치지 못했습니다',
    );
  });

  it('종료·비공개·없는 장소나 onRefresh가 없으면 버튼이 없다', () => {
    const { rerender } = render(
      <TripWeatherSummary weather={{ state: 'retired' }} date="2026-12-20" onRefresh={vi.fn()} />,
    );
    expect(screen.queryByTestId('trip-weather-refresh')).toBeNull();
    rerender(<TripWeatherSummary weather={{ state: 'no_data' }} date="2026-12-20" />);
    expect(screen.queryByTestId('trip-weather-refresh')).toBeNull();
  });

  it('결과별 안내 문구', () => {
    expect(weatherRefreshMessage({ ...BASE, failed: 1 })).toContain('연결하지 못했습니다');
    expect(weatherRefreshMessage({ ...BASE, no_data: 1 })).toContain('관측·예보 지점이 없습니다');
    expect(weatherRefreshMessage({ ...BASE, cooldown: 1 })).toContain('60초 뒤');
    expect(weatherRefreshMessage({ ...BASE, skipped: 1 })).toContain('좌표가 있는 장소');
  });
});
