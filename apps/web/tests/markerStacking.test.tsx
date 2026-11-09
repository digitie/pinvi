import type { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// #710 — 클릭한 장소 마커는 vworld-map-web Marker가 전역 z-index(1001+)로 올리고, 그 값은 `zIndex` prop이
// 바뀔 때만 풀린다. 선택 여부로 prop을 바꿔 선택이 풀리면 승격도 풀리게 한다.

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
import { MARKER_Z_BASE, MARKER_Z_SELECTED, markerZIndex } from '@/lib/markerStacking';
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
  it('비선택 0(묶음·내 위치와 같은 층, DOM 순서 유지), 선택 1', () => {
    expect(markerZIndex(false)).toBe(MARKER_Z_BASE);
    expect(markerZIndex(true)).toBe(MARKER_Z_SELECTED);
    expect(MARKER_Z_BASE).toBe(0);
    expect(MARKER_Z_SELECTED).toBeGreaterThan(MARKER_Z_BASE);
  });

  it('교통 마커는 층 zIndex를 받고, 선택이 바뀌면 그 값이 바뀐다', () => {
    seen.props = [];
    const { rerender } = render(
      <TransportMarkers points={[point('a'), point('b')]} selectedId="a" onSelect={() => {}} />,
    );
    const first = Object.fromEntries(seen.props.map((p) => [p.interactionId, p.zIndex]));
    expect(first).toEqual({ a: markerZIndex(true), b: markerZIndex(false) });
    seen.props = [];
    rerender(<TransportMarkers points={[point('a'), point('b')]} selectedId={null} onSelect={() => {}} />);
    const after = Object.fromEntries(seen.props.map((p) => [p.interactionId, p.zIndex]));
    expect(after).toEqual({ a: markerZIndex(false), b: markerZIndex(false) });
  });
});
