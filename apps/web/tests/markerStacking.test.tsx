import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// #710 — 클릭한 장소 마커는 vworld-map-web Marker가 전역 z-index(1001+)로 올리고, 그 값은 `zIndex` prop이
// 바뀔 때만 풀린다. PinVi가 층마다 고정 zIndex를 주고 선택이 바뀌면 그 값을 바꿔, 선택이 풀리면 원래 층으로
// 돌아가고 같은 자리의 교통 마커를 계속 덮지 않게 한다.

const seen = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }));

vi.mock('@/components/map/vworldPrimitives', () => ({
  ClusterLayer: ({
    points,
    renderMarker,
  }: {
    points: unknown[];
    renderMarker: (point: unknown) => ReactNode;
  }) => <>{points.map((point) => renderMarker(point))}</>,
  MakiMarker: (props: Record<string, unknown>) => {
    seen.props.push(props);
    return null;
  },
}));

import { TransportMarkers } from '@/components/map/TransportMarkers';
import { MARKER_Z, markerZIndex } from '@/lib/markerStacking';
import type { TransportMapPoint } from '@/lib/useTransportLayers';

const point = (id: string): TransportMapPoint =>
  ({
    id,
    lngLat: [126.8, 37.56],
    layer: 'airport',
    featureId: id,
    title: '김포국제공항',
    icon: 'airport',
    color: '#000',
    markerColor: 'P-01',
  }) as unknown as TransportMapPoint;

describe('마커 층(z-index) — #710', () => {
  it('층 순서: 장소 < 선택 장소 < 교통 < 선택 교통 < 여행 핀 < 선택 여행 핀', () => {
    const order = [
      markerZIndex('feature', false),
      markerZIndex('feature', true),
      markerZIndex('transport', false),
      markerZIndex('transport', true),
      markerZIndex('tripPoi', false),
      markerZIndex('tripPoi', true),
    ];
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(new Set(order).size).toBe(order.length);
    // 클릭 승격(1001+)보다 한참 아래 — 선택이 바뀌면 prop이 바뀌어 승격이 풀린다.
    expect(Math.max(...Object.values(MARKER_Z))).toBeLessThan(100);
  });

  it('교통 마커는 층 zIndex를 받고, 선택이 바뀌면 그 값이 바뀐다', () => {
    seen.props = [];
    const { rerender } = render(
      <TransportMarkers points={[point('a'), point('b')]} selectedId="a" onSelect={() => {}} />,
    );
    const first = Object.fromEntries(seen.props.map((p) => [p.interactionId, p.zIndex]));
    expect(first).toEqual({ a: markerZIndex('transport', true), b: markerZIndex('transport', false) });
    seen.props = [];
    rerender(<TransportMarkers points={[point('a'), point('b')]} selectedId={null} onSelect={() => {}} />);
    const after = Object.fromEntries(seen.props.map((p) => [p.interactionId, p.zIndex]));
    expect(after).toEqual({ a: markerZIndex('transport', false), b: markerZIndex('transport', false) });
  });
});
