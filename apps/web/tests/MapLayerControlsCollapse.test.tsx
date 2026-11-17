import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MapLayerControls } from '@/components/map/MapLayerControls';
import type { FeatureGeometryState } from '@/lib/useFeatureGeometry';

function geometry(): FeatureGeometryState {
  return {
    features: [],
    kinds: ['route'],
    toggle: vi.fn(),
    selection: null,
    select: vi.fn(),
    clearSelection: vi.fn(),
    onViewportChange: vi.fn(),
    retry: vi.fn(),
    eligible: true,
    loading: false,
    error: null,
    truncated: false,
  };
}

/**
 * 전체 화면 탐색 지도의 레이어 패널은 접을 수 있다(소유자 요청 2026-11-17). 처음엔 펼쳐 둔다 — live e2e의
 * `waitForControls`가 체크박스를 바로 본다. 여행 지도(`collapsible` 없음)는 그대로다.
 */
describe('MapLayerControls collapsible', () => {
  it('처음엔 펼쳐져 체크박스가 보이고, 접으면 레이어 버튼만 남았다가 다시 펼친다', async () => {
    const user = userEvent.setup();
    const state = geometry();
    render(
      <MapLayerControls
        geometry={state}
        transport={null}
        onOpenTransportDetail={vi.fn()}
        collapsible
      />,
    );
    const panel = screen.getByTestId('map-layer-controls');
    expect(panel).toHaveAttribute('data-collapsed', 'false');
    expect(screen.getByRole('checkbox', { name: '경로' })).toBeChecked();

    await user.click(screen.getByRole('button', { name: '지도 레이어 접기' }));
    expect(screen.getByTestId('map-layer-controls')).toHaveAttribute('data-collapsed', 'true');
    expect(screen.queryByRole('checkbox', { name: '경로' })).toBeNull();
    // 켠 레이어는 끄지 않는다 — 접기는 패널만 숨긴다.
    expect(state.toggle).not.toHaveBeenCalled();
    const reopen = screen.getByRole('button', { name: '레이어' });
    expect(reopen).toHaveAttribute('aria-expanded', 'false');

    await user.click(reopen);
    expect(screen.getByRole('checkbox', { name: '경로' })).toBeChecked();
  });

  it('collapsible이 아니면(여행 지도) 접기 버튼이 없다', () => {
    render(
      <MapLayerControls geometry={geometry()} transport={null} onOpenTransportDetail={vi.fn()} />,
    );
    expect(screen.queryByTestId('map-layer-controls-toggle')).toBeNull();
    expect(screen.getByTestId('map-layer-controls')).not.toHaveAttribute('data-collapsed');
  });
});
