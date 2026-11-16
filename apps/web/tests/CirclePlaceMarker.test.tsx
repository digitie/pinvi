import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TripWeatherCard } from '@pinvi/schemas';

const markerProps = vi.hoisted(() => ({ last: null as Record<string, unknown> | null }));

vi.mock('@/components/map/vworldPrimitives', () => ({
  Marker: ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => {
    markerProps.last = props;
    return <div data-testid="marker-root">{children}</div>;
  },
}));

import { CirclePlaceMarker } from '@/components/map/CirclePlaceMarker';

const rainyCard = (): TripWeatherCard => ({
  asof: new Date().toISOString(),
  latest_at: null,
  is_stale: false,
  source_styles: ['nowcast'],
  metrics: [
    {
      metric_key: 'PTY',
      forecast_style: 'nowcast',
      provider: 'python-kma-api',
      observed_at: new Date(Date.now() - 5 * 60_000).toISOString(),
      value_number: 1,
    },
  ],
});

afterEach(() => vi.useRealTimers());

describe('CirclePlaceMarker(구글 지도식 원형 마커)', () => {
  it('원의 중심을 좌표에 건다 — 왼쪽 가운데 앵커를 반지름만큼 왼쪽으로', () => {
    render(
      <CirclePlaceMarker lngLat={[127, 37]} color="#E53935" size={22} icon={<i />} label="경복궁" />,
    );
    expect(markerProps.last).toMatchObject({ anchor: 'left', offset: [-11, 0] });
    const dot = screen.getByTestId('circle-place-marker-dot');
    expect(dot).toHaveStyle({ width: '22px', height: '22px' });
    expect(dot.className).toContain('rounded-full');
  });

  it('이름은 배경 상자 없이 글자만(흰 halo) — 날씨를 알면 옆에 아이콘', () => {
    render(
      <CirclePlaceMarker
        lngLat={[127, 37]}
        color="#E53935"
        size={22}
        icon={<i />}
        label="경복궁"
        weather={{ poiId: 'p1', dayCard: rainyCard() }}
      />,
    );
    const label = screen.getByText('경복궁');
    expect(label.style.backgroundColor).toBe('');
    expect(label.className).not.toMatch(/\bbg-|\bshadow-|\bborder/);
    expect(label.style.textShadow).toContain('#fff');
    const glyph = screen.getByTestId('place-weather-glyph');
    expect(glyph).toHaveAttribute('data-weather-kind', 'rain');
    // 마커 버튼이 이미 이름을 가지므로 라벨·날씨는 읽기에서 숨긴다(중복 낭독 방지).
    expect(screen.getByTestId('circle-place-marker-label')).toHaveAttribute('aria-hidden', 'true');
  });

  it('날씨를 모르면 아이콘 없이 이름만, 라벨도 없으면 원만', () => {
    const { unmount } = render(
      <CirclePlaceMarker
        lngLat={[127, 37]}
        color="#E53935"
        size={22}
        icon={<i />}
        label="경복궁"
        weather={{ poiId: 'p1', dayCard: null }}
      />,
    );
    expect(screen.getByText('경복궁')).toBeInTheDocument();
    expect(screen.queryByTestId('place-weather-glyph')).toBeNull();
    unmount();
    render(<CirclePlaceMarker lngLat={[127, 37]} color="#E53935" size={18} icon={<i />} />);
    expect(screen.queryByTestId('circle-place-marker-label')).toBeNull();
  });
});
