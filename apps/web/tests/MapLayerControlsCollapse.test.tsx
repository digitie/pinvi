import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { TransportLayer } from '@pinvi/schemas';
import { describe, expect, it, vi } from 'vitest';
import { MapLayerControls } from '@/components/map/MapLayerControls';
import type { TransportLayersState } from '@/lib/useTransportLayers';

function transport(): TransportLayersState {
  return {
    visible: true,
    status: { enabled: true, layers: [] },
    enabled: new Set<TransportLayer>(['fuel_station']),
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
  };
}

/**
 * 전체 화면 탐색 지도의 레이어 패널은 접을 수 있다(소유자 요청 2026-11-17). 처음엔 펼쳐 둔다 — live e2e의
 * `waitForControls`가 체크박스를 바로 본다. 여행 지도(`collapsible` 없음)는 그대로다.
 */
describe('MapLayerControls collapsible', () => {
  it('처음엔 펼쳐져 체크박스가 보이고, 접으면 레이어 버튼만 남았다가 다시 펼친다', async () => {
    const user = userEvent.setup();
    const state = transport();
    render(<MapLayerControls transport={state} onOpenTransportDetail={vi.fn()} collapsible />);
    const panel = screen.getByTestId('map-layer-controls');
    expect(panel).toHaveAttribute('data-collapsed', 'false');
    expect(screen.getByRole('checkbox', { name: '주유소' })).toBeChecked();

    await user.click(screen.getByRole('button', { name: '지도 레이어 접기' }));
    expect(screen.getByTestId('map-layer-controls')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.queryByRole('checkbox', { name: '주유소' })).toBeNull();
    // 켠 레이어는 끄지 않는다 — 접기는 패널만 숨긴다.
    expect(state.toggle).not.toHaveBeenCalled();
    const reopen = screen.getByRole('button', { name: '레이어' });
    expect(reopen).toHaveAttribute('aria-expanded', 'false');

    await user.click(reopen);
    expect(screen.getByRole('checkbox', { name: '주유소' })).toBeChecked();
  });

  it('collapsible이 아니면(여행 지도) 접기 버튼이 없다', () => {
    render(<MapLayerControls transport={transport()} onOpenTransportDetail={vi.fn()} />);
    expect(screen.queryByTestId('map-layer-controls-toggle')).toBeNull();
    expect(screen.getByTestId('map-layer-controls')).not.toHaveAttribute('data-collapsed');
  });

  it('교통 레이어 기능이 꺼져 있으면 패널을 그리지 않는다', () => {
    const { container } = render(
      <MapLayerControls
        transport={{ ...transport(), visible: false }}
        onOpenTransportDetail={vi.fn()}
        collapsible
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
