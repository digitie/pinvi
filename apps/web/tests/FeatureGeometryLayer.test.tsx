import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { MapMouseEvent, PolygonAreaProps, RouteLineProps } from 'vworld-map-web';
import type { FeatureGeometry } from '@pinvi/schemas';
import type { GeometryFeature } from '@/lib/featureGeometry';
import type { FeatureGeometryState } from '@/lib/useFeatureGeometry';
import {
  FeatureGeometryControls,
  FeatureGeometryLayers,
  FeatureGeometryPopup,
} from '@/components/map/FeatureGeometryLayer';

const captures = vi.hoisted(() => ({
  lines: [] as RouteLineProps[],
  areas: [] as PolygonAreaProps[],
}));
vi.mock('@/components/map/vworldPrimitives', () => ({
  RouteLine: (props: RouteLineProps) => {
    captures.lines.push(props);
    return null;
  },
  PolygonArea: (props: PolygonAreaProps) => {
    captures.areas.push(props);
    return null;
  },
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
const ring: [number, number][] = [
  [127, 37],
  [127.1, 37],
  [127.1, 37.1],
  [127, 37],
];
const hole: [number, number][] = [
  [127.01, 37.01],
  [127.02, 37.01],
  [127.02, 37.02],
  [127.01, 37.01],
];
const geometries: FeatureGeometry[] = [
  {
    type: 'LineString',
    coordinates: [
      [127, 37],
      [127.1, 37.1],
    ],
  },
  {
    type: 'MultiLineString',
    coordinates: [
      [
        [127, 37],
        [127.1, 37.1],
      ],
      [
        [128, 38],
        [128.1, 38.1],
      ],
    ],
  },
  { type: 'Polygon', coordinates: [ring, hole] },
  { type: 'MultiPolygon', coordinates: [[ring, hole], [ring]] },
];
const features = geometries.map((geometry, index) => ({
  feature_id: 'opaque:/' + index,
  kind: index < 2 ? 'route' : 'area',
  name: '도형 ' + index,
  coord: null,
  marker_color: 'P-06',
  marker_icon: 'walking',
  geometry,
})) as GeometryFeature[];
function state(overrides: Partial<FeatureGeometryState> = {}): FeatureGeometryState {
  return {
    features,
    kinds: ['route', 'area'],
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
    ...overrides,
  };
}
beforeEach(() => {
  captures.lines = [];
  captures.areas = [];
});

describe('geometry layers', () => {
  it('네 종류 geometry/내부 ring을 그대로 전달하고 기존 팔레트 hex를 사용한다', () => {
    render(<FeatureGeometryLayers state={state()} />);
    expect(
      captures.lines.map((x) =>
        typeof x.data === 'object' && 'geometry' in x.data ? x.data.geometry : null,
      ),
    ).toEqual(geometries.slice(0, 2));
    expect(
      captures.areas.map((x) =>
        typeof x.data === 'object' && 'geometry' in x.data ? x.data.geometry : null,
      ),
    ).toEqual(geometries.slice(2));
    for (const line of captures.lines) expect(line.color).toMatch(/^#[0-9a-f]{6}$/i);
    for (const area of captures.areas) {
      expect(area.outlineColor).toMatch(/^#[0-9a-f]{6}$/i);
      expect(area.fillColor).toMatch(/^rgba\(\d+,\d+,\d+,0\.18\)$/);
    }
    expect(captures.lines[0]?.id).toBe('pinvi-geometry-opaque%3A%2F0');
  });
  it('겹친 layer가 같은 DOM 클릭을 각각 전달해도 최상단 hit 하나만 선택한다', () => {
    const current = state();
    render(<FeatureGeometryLayers state={current} />);
    const originalEvent = new MouseEvent('click');
    const queryRenderedFeatures = vi.fn(() => [
      { properties: { feature_id: features[1]?.feature_id } },
      { properties: { feature_id: features[2]?.feature_id } },
    ]);
    const event = {
      originalEvent,
      point: { x: 1, y: 2 },
      lngLat: { lng: 127, lat: 37 },
      target: { getLayer: vi.fn(() => ({})), queryRenderedFeatures },
    } as unknown as MapMouseEvent;
    captures.areas[0]?.onClick?.({ ...event } as MapMouseEvent);
    captures.lines[1]?.onClick?.({ ...event } as MapMouseEvent);
    expect(current.select).toHaveBeenCalledTimes(1);
    expect(current.select).toHaveBeenCalledWith(features[1], [127, 37]);
    expect(queryRenderedFeatures).toHaveBeenCalledTimes(1);
  });
  it('popup은 장소 추가 제스처에서 제외하고 원래 coord를 만들지 않는다', () => {
    const current = state({ selection: { feature: features[2]!, anchor: [127.03, 37.03] } });
    const open = vi.fn();
    render(<FeatureGeometryPopup state={current} onOpenDetail={open} />);
    expect(screen.getByTestId('geometry-popup')).toHaveAttribute('data-map-overlay', '');
    expect(screen.queryByRole('button', { name: /추가/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('geometry-detail-open'));
    expect(open).toHaveBeenCalledWith(features[2]?.feature_id);
    expect(features[2]?.coord).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '경로·영역 닫기' }));
    expect(current.clearSelection).toHaveBeenCalledOnce();
  });
  it('토글과 목록 선택을 키보드로 실행하고 부분 결과·재시도도 안내한다', async () => {
    const user = userEvent.setup(),
      current = state({ truncated: true, error: '조회 실패' });
    render(<FeatureGeometryControls state={current} />);
    await user.click(screen.getByRole('checkbox', { name: '경로 표시' }));
    expect(current.toggle).toHaveBeenCalledWith('route', false);
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(current.retry).toHaveBeenCalledOnce();
    expect(screen.getByText(/일부 경로·영역만/)).toBeVisible();
    fireEvent.click(screen.getByText(/경로·영역 목록/));
    const item = screen.getAllByTestId('geometry-list-item')[0]!;
    item.focus();
    await user.keyboard('{Enter}');
    expect(current.select).toHaveBeenCalledWith(features[0], undefined, true);
  });
});
