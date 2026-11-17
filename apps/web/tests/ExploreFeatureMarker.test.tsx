import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const markerProps = vi.hoisted(() => ({ last: null as Record<string, unknown> | null }));

vi.mock('@/components/map/vworldPrimitives', () => ({
  Marker: ({
    children,
    onClick,
    ...props
  }: { children?: ReactNode; onClick?: () => void } & Record<string, unknown>) => {
    markerProps.last = props;
    return (
      <div data-testid="marker-root" onClick={onClick}>
        {children}
      </div>
    );
  },
}));

import {
  EXPLORE_ICON_SIZE,
  EXPLORE_MARKER_CLASS,
  EXPLORE_MARKER_SIZE,
  ExploreFeatureMarker,
} from '@/components/map/ExploreFeatureMarker';
import type { ExploreMapPoint } from '@/lib/exploreMapPoints';

const point: ExploreMapPoint = {
  id: 'f-1',
  lngLat: [126.977, 37.579],
  kind: 'feature',
  color: '#8E24AA',
  markerColor: 'P-09',
  markerSource: 'upstream',
  icon: 'museum',
  title: '국립중앙박물관',
  lon: 126.977,
  lat: 37.579,
  category: '미술관/박물관',
  featureId: 'f-1',
};

/**
 * 소유자 요청 2026-11-17 "탐색지도의 마커도 여행과 동일하게" — 탐색 지도 장소 마커는 여행 지도 장소 마커와
 * 같은 컴포넌트(`CirclePlaceMarker`)·크기(22/13)로 원 + 상자 없는 이름 라벨을 그린다.
 */
describe('ExploreFeatureMarker(탐색 지도 장소 마커 = 여행 지도 마커 모양)', () => {
  it('여행 지도와 같은 원(22px, 원 중심 = 좌표) + 이름 라벨 + 탐색 지도 class', () => {
    render(<ExploreFeatureMarker point={point} selected={false} onSelect={vi.fn()} />);
    expect(EXPLORE_MARKER_SIZE).toBe(22);
    expect(EXPLORE_ICON_SIZE).toBe(13);
    expect(markerProps.last).toMatchObject({
      anchor: 'left',
      offset: [-11, 0],
      className: EXPLORE_MARKER_CLASS,
      ariaLabel: '국립중앙박물관',
      interactionId: 'feature:f-1',
      selected: false,
    });
    // 이름은 라벨로 늘 보이므로 hover 상자(title)는 없다(여행 지도와 같다).
    expect(markerProps.last?.title).toBeUndefined();
    const dot = screen.getByTestId('circle-place-marker-dot');
    expect(dot).toHaveStyle({ width: '22px', height: '22px', backgroundColor: '#8E24AA' });
    expect(screen.getByTestId('circle-place-marker-label')).toHaveTextContent('국립중앙박물관');
  });

  it('장소별 날씨가 없으므로 날씨 아이콘은 그리지 않는다', () => {
    render(<ExploreFeatureMarker point={point} selected={false} onSelect={vi.fn()} />);
    expect(screen.queryByTestId('place-weather-glyph')).toBeNull();
  });

  it('누르면 그 point로 선택을 알린다(라벨도 마커의 일부)', () => {
    const onSelect = vi.fn();
    render(<ExploreFeatureMarker point={point} selected onSelect={onSelect} />);
    expect(markerProps.last).toMatchObject({ selected: true });
    fireEvent.click(screen.getByText('국립중앙박물관'));
    expect(onSelect).toHaveBeenCalledWith(point);
  });
});
