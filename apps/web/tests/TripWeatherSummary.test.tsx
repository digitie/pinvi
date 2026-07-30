import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { FeatureWeatherResolution } from '@pinvi/schemas';
import { TripWeatherSummary } from '@/components/trips/TripWeatherSummary';

function foundWeather(): FeatureWeatherResolution {
  return {
    state: 'found',
    card: {
      feature_id: 'weather:found',
      asof: '2026-07-30T00:00:00+09:00',
      latest_at: '2026-07-30T15:00:00+09:00',
      is_stale: false,
      source_styles: ['observed', 'short'],
      metrics: [
        {
          forecast_style: 'observed',
          metric_key: 'T1H',
          metric_name: '기온',
          effective_at: '2026-07-29T15:00:00Z',
          observed_at: '2026-07-29T15:00:00Z',
          value_number: 24,
          unit: '℃',
        },
        {
          forecast_style: 'short',
          metric_key: 'TMP',
          metric_name: '기온',
          valid_from: '2026-07-30T09:00:00Z',
          value_number: 27,
          unit: '℃',
        },
        {
          forecast_style: 'short',
          metric_key: 'TMP',
          metric_name: '기온',
          issued_at: '2026-07-30T12:00:00+09:00',
          value_number: 99,
          unit: '℃',
        },
      ],
    },
  };
}

describe('TripWeatherSummary', () => {
  it('서버 batch의 found card를 별도 요청 없이 표시한다', () => {
    render(<TripWeatherSummary weather={foundWeather()} date="2026-07-30" />);

    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('현재');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('24℃');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('예보');
    expect(screen.getByTestId('trip-weather-summary')).toHaveTextContent('27℃');
    expect(screen.getByTestId('trip-weather-summary')).not.toHaveTextContent('99℃');
  });

  it.each([
    ['no_data', '이 날짜의 날씨 정보가 없습니다.'],
    ['retired', '장소 상태가 종료되어 날씨를 확인할 수 없습니다.'],
    ['suppressed', '비공개 장소는 날씨를 확인할 수 없습니다.'],
    ['missing', '장소 정보를 찾을 수 없어 날씨를 확인할 수 없습니다.'],
    ['unavailable', '날씨 서비스를 일시적으로 사용할 수 없습니다.'],
  ] as const)('%s 상태를 구분해 표시한다', (state, message) => {
    render(<TripWeatherSummary weather={{ state }} date="2026-07-30" />);

    expect(screen.getByTestId('trip-weather-status')).toHaveTextContent(message);
  });
});
