import { createRef, type ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { VWorldMapViewProps, MarkerProps, MapLibreMap } from 'vworld-map-web';
import type { VWorldMapHandle } from '../../mobile/components/VWorldMap.types';
import { WebVWorldMap } from '../../mobile/components/VWorldMapWeb';

const observed = vi.hoisted(() => ({
  props: null as VWorldMapViewProps | null,
  marker: null as MarkerProps | null,
}));
vi.mock('vworld-map-rn', () => {
  throw new Error('native-only engine evaluated on web');
});
vi.mock('react-native', () => ({
  View: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock('../../mobile/components/ui', () => ({
  Muted: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
}));
vi.mock('vworld-map-web', () => ({
  VWorldMapView: (props: VWorldMapViewProps) => {
    observed.props = props;
    return <section>{props.children}</section>;
  },
  Marker: (props: MarkerProps) => {
    observed.marker = props;
    return (
      <button
        aria-label={props.ariaLabel}
        onClick={() => props.onClick?.({} as never, {} as never, {} as never)}
      >
        {props.children}
      </button>
    );
  },
}));

beforeEach(() => {
  observed.props = null;
  observed.marker = null;
});

describe('Expo web public VWorld adapter', () => {
  it('카메라 명령·bbox·좌표순서를 보존하고 추가 위치권한 제어를 끈다', () => {
    const ref = createRef<VWorldMapHandle>();
    const camera = vi.fn();
    const map = {
      flyTo: vi.fn(),
      fitBounds: vi.fn(),
      zoomTo: vi.fn(),
      getCenter: () => ({ lng: 127, lat: 37 }),
      getZoom: () => 12,
      getBounds: () => ({
        getNorthEast: () => ({ lng: 128, lat: 38 }),
        getSouthWest: () => ({ lng: 126, lat: 36 }),
      }),
    };
    render(
      <WebVWorldMap
        ref={ref}
        apiKey=""
        initialCenter={[127, 37]}
        initialZoom={12}
        mapType="hybrid"
        onCameraChanged={camera}
      />,
    );
    const props = observed.props!;
    expect(props).toMatchObject({
      layerType: 'Hybrid',
      center: [127, 37],
      zoom: 12,
      navigation: false,
      geolocate: false,
      scale: false,
    });
    props.onLoad?.(map as unknown as MapLibreMap);
    expect(camera).toHaveBeenLastCalledWith({
      center: [127, 37],
      zoom: 12,
      bounds: { ne: [128, 38], sw: [126, 36] },
    });
    ref.current?.flyTo({ center: [129, 35], zoom: 14, durationMs: 300 });
    expect(map.flyTo).toHaveBeenCalledWith({ center: [129, 35], zoom: 14, duration: 300 });
    ref.current?.fitBounds({ ne: [128, 38], sw: [126, 36] }, { paddingPx: 20, durationMs: 200 });
    expect(map.fitBounds).toHaveBeenCalledWith(
      [
        [126, 36],
        [128, 38],
      ],
      { padding: 20, duration: 200 },
    );
    ref.current?.zoomTo(10, 100);
    expect(map.zoomTo).toHaveBeenCalledWith(10, { duration: 100 });
    props.onMoveEnd?.({} as never);
    expect(camera).toHaveBeenCalledTimes(2);
  });

  it('공개 Marker로 선택한 원본 feature를 전달하고 ID·접근성·적층 순서를 보존한다', () => {
    const press = vi.fn();
    const marker = {
      id: 'place-1',
      coordinate: [127, 37] as [number, number],
      ariaLabel: '선택한 장소',
      color: '#123456',
      selected: true,
      zIndex: 5,
    };
    render(<WebVWorldMap apiKey="" markers={[marker]} onFeaturePress={press} />);
    expect(observed.marker).toMatchObject({
      lngLat: [127, 37],
      interactionId: 'place-1',
      zIndex: 5,
      ariaLabel: '선택한 장소',
    });
    fireEvent.click(screen.getByRole('button', { name: '선택한 장소' }));
    expect(press).toHaveBeenCalledWith(marker);
  });
});
