import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import { MapLayerControls } from '@/components/map/MapLayerControls';
import type { TransportDetailTarget, TransportLayersState } from '@/lib/useTransportLayers';

// 지도 레이어 패널(교통 레이어만 있다 — 경로·영역은 2026-11-27 제거).
function TransportLayerControls({
  state,
  onOpenDetail,
  collapseIncidents,
}: {
  state: TransportLayersState;
  onOpenDetail: (target: TransportDetailTarget) => void;
  collapseIncidents?: boolean;
}) {
  return (
    <MapLayerControls
      transport={state}
      onOpenTransportDetail={onOpenDetail}
      collapseIncidents={collapseIncidents}
    />
  );
}

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
    hasMap: true,
    nearMode: false,
    radiusM: null,
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

  it('레이어 체크박스를 누르면 toggle을 부른다', () => {
    const state = makeState({ enabled: new Set<TransportLayer>(['highway_incident']) });
    render(<TransportLayerControls state={state} onOpenDetail={vi.fn()} />);
    const fuel = screen.getByRole('checkbox', { name: '주유소' });
    expect(fuel).toHaveAttribute('data-testid', 'transport-layer-toggle-fuel_station');
    expect(fuel).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: '교통 돌발' })).toBeChecked();
    fireEvent.click(fuel);
    expect(state.toggle).toHaveBeenCalledWith('fuel_station');
  });

  it('공항·휴게소·경로·영역은 없고, 주유소·교통 돌발 체크박스만 있다', () => {
    render(<MapLayerControls transport={makeState({})} onOpenTransportDetail={vi.fn()} />);
    const group = screen.getByRole('group', { name: '지도 레이어 표시' });
    const names = Array.from(group.querySelectorAll('label')).map((l) => l.textContent);
    expect(names).toEqual(['주유소', '교통 돌발']);
    expect(screen.queryByRole('checkbox', { name: '경로' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: '영역' })).toBeNull();
    expect(screen.queryByText('공항')).toBeNull();
    expect(screen.queryByText('휴게소')).toBeNull();
    expect(screen.queryByTestId('transport-layer-toggle-airport')).toBeNull();
    expect(screen.queryByTestId('transport-layer-toggle-rest_area')).toBeNull();
    // 예전 별도 '교통 정보' 패널 제목은 없다.
    expect(screen.queryByText('교통 정보')).toBeNull();
  });

  it('여행 장소 반경 모드는 줌 안내 없이 반경을 알린다', () => {
    render(
      <TransportLayerControls
        state={makeState({
          nearMode: true,
          radiusM: { fuel_station: 10_000, highway_incident: 20_000 },
          zoom: 6,
          enabled: new Set<TransportLayer>(['fuel_station', 'highway_incident']),
          results: [
            { layer: 'fuel_station', status: 'ok', truncated: true, freshness: FRESHNESS, items: [] },
            { layer: 'highway_incident', status: 'ok', truncated: false, items: [] },
          ],
        })}
        onOpenDetail={vi.fn()}
      />,
    );
    const fuel = screen.getByTestId('transport-layer-state-fuel_station');
    expect(fuel).not.toHaveTextContent('확대하면 보여요');
    expect(fuel).toHaveTextContent('0곳 · 여행 장소 10km 이내 · 가까운 곳만 표시');
    expect(screen.getByTestId('transport-layer-state-highway_incident')).toHaveTextContent(
      '여행 장소 20km 이내',
    );
  });

  it('켠 레이어는 결과 전에도 "불러오는 중" 한 줄을 미리 차지한다(#712)', () => {
    // 결과가 와서 줄이 새로 생기면 패널 상시 부분이 자라 여행 지도가 다시 맞춰지고 같은 레이어를 다시
    // 조회한다(운영 mobile 2026-11-08). 켠 순간 줄을 차지해 두면 결과가 와도 상시 높이가 그대로다.
    render(
      <TransportLayerControls
        state={makeState({
          zoom: 9,
          enabled: new Set<TransportLayer>(['highway_incident']),
          results: [],
        })}
        onOpenDetail={vi.fn()}
      />,
    );
    const line = screen.getByTestId('transport-layer-state-highway_incident');
    expect(line).toHaveTextContent('불러오는 중');
    expect(line).toHaveAttribute('data-status', 'loading');
    // 두 줄 높이 고정 — 결과 문구 길이로 줄 수가 바뀌지 않게, 그러나 경고 문구는 자르지 않게.
    expect(line.className).toContain('line-clamp-2');
    expect(line.className).toContain('min-h-[2lh]');
  });

  it('지도가 없으면(fallback) "불러오는 중"을 띄우지 않는다', () => {
    render(
      <TransportLayerControls
        state={makeState({
          hasMap: false,
          enabled: new Set<TransportLayer>(['highway_incident']),
          results: [],
        })}
        onOpenDetail={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('transport-layer-state-highway_incident')).toBeNull();
  });

  it('줌 안내·강등·신선도·잘림을 레이어별로 보인다', () => {
    const results: TransportLayerResult[] = [
      { layer: 'highway_incident', status: 'ok', truncated: true, freshness: FRESHNESS, items: [] },
    ];
    const { rerender } = render(
      <TransportLayerControls
        state={makeState({
          zoom: 9,
          enabled: new Set<TransportLayer>(['fuel_station', 'highway_incident']),
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
    const incidentLine = screen.getByTestId('transport-layer-state-highway_incident');
    expect(incidentLine).toHaveTextContent('일부만 표시 — 확대하세요');
    // Map age 600초 + 받은 뒤 60초.
    expect(incidentLine).toHaveTextContent('11분 전 갱신');
    rerender(
      <TransportLayerControls
        state={makeState({
          zoom: 12,
          enabled: new Set<TransportLayer>(['fuel_station']),
          results: [
            {
              layer: 'fuel_station',
              status: 'unavailable',
              reason: 'NOT_LOADED',
              truncated: false,
              items: [],
            },
          ],
        })}
        onOpenDetail={vi.fn()}
      />,
    );
    const fuel = screen.getByTestId('transport-layer-state-fuel_station');
    expect(fuel).toHaveTextContent('일시적으로 불러올 수 없음');
    expect(fuel).toHaveAttribute('data-reason', 'NOT_LOADED');
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

  describe('collapseIncidents — 여행 지도(#729)', () => {
    const incidentResults: TransportLayerResult[] = [
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
    ];

    it('돌발 목록은 결과가 와도 접혀 있고 상태 줄을 누르면 펴고 접는다', () => {
      // 맞춤 뒤에 목록이 펼쳐지면 지도 위 핀을 덮는다(운영 NEAR-025 mobile, 영월 고씨굴). 펼치는 것은 사용자다.
      const onOpenDetail = vi.fn();
      render(
        <TransportLayerControls
          state={makeState({
            enabled: new Set<TransportLayer>(['highway_incident']),
            results: incidentResults,
          })}
          onOpenDetail={onOpenDetail}
          collapseIncidents
        />,
      );
      expect(screen.queryByTestId('transport-incident-list')).toBeNull();
      const toggle = screen.getByTestId('transport-incident-toggle');
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      expect(toggle).toHaveTextContent('2곳');
      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      const list = screen.getByTestId('transport-incident-list');
      expect(toggle).toHaveAttribute('aria-controls', list.id);
      const buttons = list.querySelectorAll('button');
      expect(buttons[0]).toHaveTextContent('최근 사고');
      fireEvent.click(buttons[0]!);
      expect(onOpenDetail).toHaveBeenCalledWith({
        layer: 'highway_incident',
        featureId: 'b',
        title: '최근 사고',
      });
      fireEvent.click(toggle);
      expect(screen.queryByTestId('transport-incident-list')).toBeNull();
    });

    it('돌발 상태 줄은 불러오는 중에도 결과 뒤와 같은 터치 높이를 미리 차지한다', () => {
      // 결과가 와서 줄이 버튼(44px)으로 자라면 패널 상시 부분이 자라 다시 맞추고 다시 조회한다(#712).
      const enabled = new Set<TransportLayer>(['highway_incident']);
      const { rerender } = render(
        <TransportLayerControls
          state={makeState({ enabled, results: [] })}
          onOpenDetail={vi.fn()}
          collapseIncidents
        />,
      );
      const loading = screen.getByTestId('transport-layer-state-highway_incident');
      expect(loading).toHaveTextContent('불러오는 중');
      expect(loading.className).toContain('min-h-11');
      const loadingClass = loading.className;
      rerender(
        <TransportLayerControls
          state={makeState({ enabled, results: incidentResults })}
          onOpenDetail={vi.fn()}
          collapseIncidents
        />,
      );
      const done = screen.getByTestId('transport-layer-state-highway_incident');
      expect(done.className).toBe(loadingClass);
      expect(screen.getByTestId('transport-incident-toggle').className).toContain('min-h-11');
    });

    it('레이어를 껐다 켜면 다시 접힌 채로 시작한다', () => {
      const withIncidents = makeState({
        enabled: new Set<TransportLayer>(['highway_incident']),
        results: incidentResults,
      });
      const { rerender } = render(
        <TransportLayerControls state={withIncidents} onOpenDetail={vi.fn()} collapseIncidents />,
      );
      fireEvent.click(screen.getByTestId('transport-incident-toggle'));
      expect(screen.getByTestId('transport-incident-list')).toBeInTheDocument();
      rerender(
        <TransportLayerControls
          state={makeState({ enabled: new Set<TransportLayer>(), results: [] })}
          onOpenDetail={vi.fn()}
          collapseIncidents
        />,
      );
      rerender(
        <TransportLayerControls state={withIncidents} onOpenDetail={vi.fn()} collapseIncidents />,
      );
      expect(screen.queryByTestId('transport-incident-list')).toBeNull();
      expect(screen.getByTestId('transport-incident-toggle')).toHaveAttribute(
        'aria-expanded',
        'false',
      );
    });

    it('재조회가 0건을 돌려주면 접는다 — 다음 결과에서 목록이 저절로 펼쳐지지 않는다', () => {
      const enabled = new Set<TransportLayer>(['highway_incident']);
      const withIncidents = makeState({ enabled, results: incidentResults });
      const { rerender } = render(
        <TransportLayerControls state={withIncidents} onOpenDetail={vi.fn()} collapseIncidents />,
      );
      fireEvent.click(screen.getByTestId('transport-incident-toggle'));
      expect(screen.getByTestId('transport-incident-list')).toBeInTheDocument();
      rerender(
        <TransportLayerControls
          state={makeState({
            enabled,
            results: [{ ...incidentResults[0]!, items: [] }],
          })}
          onOpenDetail={vi.fn()}
          collapseIncidents
        />,
      );
      expect(screen.queryByTestId('transport-incident-toggle')).toBeNull();
      rerender(
        <TransportLayerControls state={withIncidents} onOpenDetail={vi.fn()} collapseIncidents />,
      );
      expect(screen.queryByTestId('transport-incident-list')).toBeNull();
    });
  });
});
