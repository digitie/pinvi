import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import { TransportLayerControls } from '@/components/map/TransportLayerControls';
import type { TransportLayersState } from '@/lib/useTransportLayers';

const FRESHNESS = {
  source_collected_at: '2026-10-23T09:00:00+09:00',
  loaded_at: '2026-10-23T09:05:00+09:00',
  age_seconds: 600,
  max_age_seconds: 172800,
  stale: false,
};

function incident(id: string, title: string, occurred_at: string | null): HighwayIncidentItem {
  return {
    layer: 'highway_incident',
    feature_id: id,
    category: '99000000',
    marker_icon: 'roadblock',
    marker_color: 'P-13',
    coord: { lon: 127.1, lat: 37.2 },
    title,
    process_status: '처리중',
    occurred_at,
  };
}

function makeState(over: Partial<TransportLayersState>): TransportLayersState {
  return {
    visible: true,
    status: { enabled: true, layers: [] },
    enabled: new Set<TransportLayer>(),
    zoom: 12,
    results: [],
    receivedAt: 1_000,
    nowMs: 1_000,
    points: [],
    selectedId: null,
    toggle: vi.fn(),
    onViewportChange: vi.fn(),
    detail: null,
    openDetail: vi.fn(),
    closeDetail: vi.fn(),
    ...over,
  };
}

describe('TransportLayerControls', () => {
  it('기능이 꺼져 있으면 아무것도 그리지 않는다', () => {
    const { container } = render(
      <TransportLayerControls state={makeState({ visible: false })} onOpenDetail={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('레이어 토글을 누르면 toggle을 부른다', () => {
    const state = makeState({});
    render(<TransportLayerControls state={state} onOpenDetail={vi.fn()} />);
    const fuel = screen.getByTestId('transport-layer-toggle-fuel_station');
    expect(fuel).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(fuel);
    expect(state.toggle).toHaveBeenCalledWith('fuel_station');
  });

  it('줌 안내·강등·신선도·잘림을 레이어별로 보인다', () => {
    const results: TransportLayerResult[] = [
      { layer: 'rest_area', status: 'ok', truncated: true, freshness: FRESHNESS, items: [] },
      { layer: 'airport', status: 'unavailable', reason: 'NOT_LOADED', truncated: false, items: [] },
    ];
    render(
      <TransportLayerControls
        state={makeState({
          zoom: 9,
          enabled: new Set<TransportLayer>(['fuel_station', 'rest_area', 'airport']),
          results,
          receivedAt: 1_000,
          nowMs: 61_000,
        })}
        onOpenDetail={vi.fn()}
      />,
    );
    expect(screen.getByTestId('transport-layer-state-fuel_station')).toHaveTextContent(
      '확대하면 보여요',
    );
    const rest = screen.getByTestId('transport-layer-state-rest_area');
    expect(rest).toHaveTextContent('일부만 표시 — 확대하세요');
    // Map age 600초 + 받은 뒤 60초.
    expect(rest).toHaveTextContent('11분 전 갱신');
    const airport = screen.getByTestId('transport-layer-state-airport');
    expect(airport).toHaveTextContent('일시적으로 불러올 수 없음');
    expect(airport).toHaveAttribute('data-reason', 'NOT_LOADED');
  });

  it('돌발 목록은 최근 순이고 누르면 상세를 연다', () => {
    const onOpenDetail = vi.fn();
    render(
      <TransportLayerControls
        state={makeState({
          enabled: new Set<TransportLayer>(['highway_incident']),
          results: [
            {
              layer: 'highway_incident',
              status: 'ok',
              truncated: false,
              freshness: FRESHNESS,
              items: [
                incident('a', '오래된 사고', '2026-10-23T07:00:00+09:00'),
                incident('b', '최근 사고', '2026-10-23T09:00:00+09:00'),
              ],
            },
          ],
        })}
        onOpenDetail={onOpenDetail}
      />,
    );
    const list = screen.getByTestId('transport-incident-list');
    const buttons = list.querySelectorAll('button');
    expect(buttons[0]).toHaveTextContent('최근 사고');
    fireEvent.click(buttons[0]!);
    expect(onOpenDetail).toHaveBeenCalledWith({
      layer: 'highway_incident',
      featureId: 'b',
      title: '최근 사고',
    });
  });
});
