import React from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AdminFeatureWeatherValuesResponseSchema } from '@pinvi/schemas';
import { FeatureDetailSubpage } from '@/app/(admin)/admin/features/[feature_id]/FeatureDetailSubpage';

const state = vi.hoisted(() => ({ query: {} as Record<string, unknown> }));
vi.mock('next/navigation', () => ({ useParams: () => ({ feature_id: 'fixture-weather' }) }));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => state.query }));

beforeEach(() => {
  state.query = { data: null, isLoading: false, isError: false, refetch: vi.fn() };
});

it('로딩 중·빈 결과를 fresh로 표시하지 않는다', () => {
  state.query.isLoading = true;
  const view = render(<FeatureDetailSubpage tab="weather-values" />);
  expect(screen.getByTestId('admin-feature-weather-freshness')).toHaveTextContent('확인 중');
  state.query = {
    ...state.query,
    isLoading: false,
    data: AdminFeatureWeatherValuesResponseSchema.parse({ feature_id: 'fixture-weather' }),
  };
  view.rerender(<FeatureDetailSubpage tab="weather-values" />);
  expect(screen.getByTestId('admin-feature-weather-freshness')).toHaveTextContent('판정 불가');
  expect(screen.queryByText('fresh', { exact: true })).not.toBeInTheDocument();
});

it('실패한 재조회는 캐시 값이 있어도 정상 신선도로 보이지 않는다', () => {
  state.query = {
    ...state.query,
    isError: true,
    error: new Error('fixture failure'),
    data: AdminFeatureWeatherValuesResponseSchema.parse({
      feature_id: 'fixture-weather',
      latest_at: '2026-11-05T00:00:00Z',
      items: [{ metric_key: 'TMP', forecast_style: 'mid', dataset_key: null, value_number: 12 }],
    }),
  };
  render(<FeatureDetailSubpage tab="weather-values" />);
  expect(screen.getByTestId('admin-feature-weather-freshness')).toHaveTextContent('판정 불가');
});

it('값의 지연 신호와 원천 메타 부재를 구분한다', () => {
  const data = AdminFeatureWeatherValuesResponseSchema.parse({
    feature_id: 'fixture-weather',
    latest_at: '2026-11-05T00:00:00Z',
    items: [{ metric_key: 'TMP', forecast_style: 'mid', dataset_key: null, value_number: 12 }],
  });
  state.query.data = data;
  const view = render(<FeatureDetailSubpage tab="weather-values" />);
  expect(screen.getByTestId('admin-feature-weather-freshness')).toHaveTextContent('지연 신호 없음');
  state.query.data = { ...data, is_stale: true };
  view.rerender(<FeatureDetailSubpage tab="weather-values" />);
  expect(screen.getByTestId('admin-feature-weather-freshness')).toHaveTextContent('오래된 정보');
});

it('정규화 키·시각·null dataset이 같아도 다른 provider의 행·값은 정렬과 재조회 뒤 유지된다', () => {
  const metric = {
    metric_key: 'TMP',
    forecast_style: 'short',
    dataset_key: null,
    valid_at: '2026-11-05T01:00:00Z',
    known_at: '2026-11-05T00:00:00Z',
    unit: 'deg_c',
  };
  const data = AdminFeatureWeatherValuesResponseSchema.parse({
    feature_id: 'fixture-weather',
    latest_at: '2026-11-05T00:00:00Z',
    items: [
      { ...metric, provider: 'python-kma-api', value_number: 10 },
      { ...metric, provider: 'openweathermap', value_number: 12 },
    ],
  });
  state.query.data = data;
  const view = render(<FeatureDetailSubpage tab="weather-values" />);
  const check = () => {
    const rows = screen.getAllByTestId(/^admin-feature-weather-row-/);
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((row) => row.getAttribute('data-testid'))).size).toBe(2);
    expect(rows.find((row) => row.textContent?.includes('python-kma-api'))).toHaveTextContent(
      '10 deg_c',
    );
    expect(rows.find((row) => row.textContent?.includes('openweathermap'))).toHaveTextContent(
      '12 deg_c',
    );
    expect(screen.getByText('python-kma-api')).toBeVisible();
    expect(screen.getByText('openweathermap')).toBeVisible();
  };
  check();
  fireEvent.click(screen.getByRole('button', { name: /metric/ }));
  check();
  state.query.data = { ...data, items: [...data.items].reverse() };
  view.rerender(<FeatureDetailSubpage tab="weather-values" />);
  check();
});
