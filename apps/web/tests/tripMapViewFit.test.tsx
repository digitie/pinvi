import { useEffect, type ReactNode } from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TripMapPoint } from '@pinvi/domain';

// 여행 지도 맞춤의 배선(리뷰 #619): 검색 줄 기준으로 맞춘 뒤, 교통 패널 밑에 핀이 들면 패널 아래까지
// 다시 맞춘다. 패널이 늦게 나타나면 한 번 더 맞추되, 그 사이 사용자가 지도를 움직였으면 하지 않는다.
// CI e2e에는 VWorld 키가 없어 이 경로가 돌지 않으므로 지도와 패널을 대역으로 세운다.

const h = vi.hoisted(() => ({
  transportVisible: false,
  popupClose: null as (() => void) | null,
  map: null as unknown,
  onMoveEnd: null as ((event: unknown) => void) | null,
}));

vi.mock('@/components/map/vworldPrimitives', () => ({
  VWorldMap: ({
    onLoad,
    onMoveEnd,
    children,
  }: {
    onLoad?: (map: unknown) => void;
    onMoveEnd?: (event: unknown) => void;
    children?: ReactNode;
  }) => {
    h.onMoveEnd = onMoveEnd ?? null;
    useEffect(() => {
      onLoad?.(h.map);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return <div>{children}</div>;
  },
  ClusterLayer: () => null,
  PinMarker: () => null,
  Popup: ({ onClose }: { onClose?: () => void }) => {
    h.popupClose = onClose ?? null;
    return null;
  },
  MapFallback: () => null,
  MapLoadingSkeleton: () => null,
}));
vi.mock('@/lib/useTransportLayers', () => ({
  useTransportLayers: () => ({
    visible: h.transportVisible,
    onViewportChange: () => {},
    openDetail: () => {},
    closeDetail: () => {},
    points: [],
    selectedId: null,
    detail: null,
  }),
}));
vi.mock('@/components/map/TransportLayerControls', () => ({
  TransportLayerControls: () => <div data-map-fit-panel="" data-testid="fit-panel" />,
}));
vi.mock('@/components/map/TransportMarkers', () => ({
  TransportMarkers: () => null,
  TransportMarkerLegend: () => null,
}));
vi.mock('@/components/map/TransportDetailDialog', () => ({ TransportDetailDialog: () => null }));
vi.mock('@/components/map/FeatureDetailModalController', () => ({
  FeatureDetailModalController: () => null,
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => true }));

import { TripMapView } from '@/components/trips/TripMapView';

const box = (x: number, y: number, width: number, height: number) =>
  ({
    x,
    y,
    left: x,
    top: y,
    width,
    height,
    right: x + width,
    bottom: y + height,
    toJSON: () => ({}),
  }) as DOMRect;

// 모바일 재현값(390x700 지도): 검색 입력 줄 88~132, 교통 패널 x 8~264 / y 152~288, 스택 80~680.
const RECTS: Record<string, DOMRect> = {
  'fit-container': box(0, 0, 390, 700),
  'fit-anchor': box(8, 88, 374, 44),
  'fit-panel': box(8, 152, 256, 136),
  'trip-map-overlay-stack': box(8, 80, 374, 600),
};

const point = (poiId: string, lat: number): TripMapPoint =>
  ({
    poiId,
    dayIndex: 1,
    title: poiId,
    lon: 128.53,
    lat,
    color: '#000',
    markerColor: 'P-07',
    labelColor: '#fff',
    markerSource: 'resolved',
    icon: 'monument',
    category: null,
    kind: null,
    featureResolutionState: 'found',
  }) as TripMapPoint;
const POINTS = [point('north', 37.13), point('south', 36.55)];

function fakeMap(northAnchor: { x: number; y: number }) {
  const container = document.createElement('div');
  container.setAttribute('data-testid', 'fit-container');
  const canvas = document.createElement('canvas');
  return {
    getContainer: () => container,
    getCanvas: () => canvas,
    resize: vi.fn(),
    fitBounds: vi.fn(),
    flyTo: vi.fn(),
    project: vi.fn(([, lat]: [number, number]) => (lat > 37 ? northAnchor : { x: 72, y: 600 })),
    getBounds: () => ({
      getWest: () => 128,
      getSouth: () => 36,
      getEast: () => 129,
      getNorth: () => 38,
    }),
    getZoom: () => 9,
    on: vi.fn(),
    off: vi.fn(),
  };
}

const overlay = <form data-map-fit-anchor="" data-testid="fit-anchor" />;

beforeEach(() => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    return RECTS[this.getAttribute('data-testid') ?? ''] ?? box(0, 0, 0, 0);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  h.transportVisible = false;
  h.onMoveEnd = null;
  h.popupClose = null;
});

describe('TripMapView 맞춤 배선', () => {
  it('교통 패널 밑에 북쪽 핀이 들면 패널 아래까지 한 번 더 맞춘다', () => {
    h.transportVisible = true;
    const map = fakeMap({ x: 72, y: 207 });
    h.map = map;
    render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);

    expect(map.fitBounds).toHaveBeenCalledTimes(2);
    // 1차: 검색 줄 아래(132) + 핀 48 + 간격 24
    expect(map.fitBounds.mock.calls[0]?.[1].padding.top).toBe(132 + 48 + 24);
    // 2차: 패널 아래(288) + 핀 48 + 간격 24
    expect(map.fitBounds.mock.calls[1]?.[1].padding.top).toBe(288 + 48 + 24);
  });

  it('패널 밑에 핀이 없으면 다시 맞추지 않는다', () => {
    h.transportVisible = true;
    const map = fakeMap({ x: 300, y: 207 });
    h.map = map;
    render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);

    expect(map.fitBounds).toHaveBeenCalledTimes(1);
  });

  it('장소가 하나면 가운데 열을 덮는 패널 아래를 기준으로 내린다(모바일)', () => {
    h.transportVisible = true;
    const map = fakeMap({ x: 195, y: 350 });
    h.map = map;
    render(<TripMapView points={[POINTS[0]!]} transportLayers overlayTopLeft={overlay} />);

    expect(map.fitBounds).not.toHaveBeenCalled();
    expect(map.flyTo).toHaveBeenCalledTimes(1);
    // (패널 아래 288 + 48 + 24) - 아래 여백 64, 절반
    expect(map.flyTo.mock.calls[0]?.[0].offset).toEqual([0, (288 + 48 + 24 - 64) / 2]);
  });

  it('장소가 하나라도 패널이 가운데 열 밖이면(데스크톱) 검색 줄만 기준으로 한다', () => {
    RECTS['fit-container'] = box(0, 0, 1000, 800);
    try {
      h.transportVisible = true;
      const map = fakeMap({ x: 500, y: 400 });
      h.map = map;
      render(<TripMapView points={[POINTS[0]!]} transportLayers overlayTopLeft={overlay} />);

      expect(map.flyTo.mock.calls[0]?.[0].offset).toEqual([0, (132 + 48 + 24 - 64) / 2]);
    } finally {
      RECTS['fit-container'] = box(0, 0, 390, 700);
    }
  });

  it('패널이 늦게 나타나면 다시 맞추고, 그 사이 사용자가 움직였으면 하지 않는다', () => {
    const map = fakeMap({ x: 72, y: 207 });
    h.map = map;
    const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
    // 맞춤 자신이 내는 moveend(originalEvent 없음)는 사용자 이동이 아니다
    h.onMoveEnd?.({ target: map });

    h.transportVisible = true;
    view.rerender(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    expect(map.fitBounds).toHaveBeenCalledTimes(3);
    expect(map.fitBounds.mock.calls[2]?.[1].padding.top).toBe(288 + 48 + 24);

    // 새로 마운트: 로드 뒤 사용자가 끌어 옮기고 나서 패널이 나타난다
    view.unmount();
    h.transportVisible = false;
    const moved = fakeMap({ x: 72, y: 207 });
    h.map = moved;
    const second = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    h.onMoveEnd?.({ target: moved, originalEvent: new MouseEvent('mouseup') });
    h.transportVisible = true;
    second.rerender(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    expect(moved.fitBounds).toHaveBeenCalledTimes(1);
  });
});

it('제어된 POI popup이 native로 닫히면 선택 해제를 소유자에게 전달한다', () => {
  h.map = fakeMap({ x: 300, y: 300 });
  const select = vi.fn();
  render(<TripMapView points={POINTS} selectedPoiId="north" onSelectPoi={select} />);
  expect(h.popupClose).toEqual(expect.any(Function));
  h.popupClose!();
  expect(select).toHaveBeenCalledWith(null);
});

it('외부 POI 선택은 가운데 열의 검색·교통 패널 아래로 offset을 준다', () => {
  h.transportVisible = true;
  const map = fakeMap({ x: 72, y: 207 });
  h.map = map;
  const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
  map.flyTo.mockClear();
  view.rerender(
    <TripMapView points={POINTS} selectedPoiId="north" transportLayers overlayTopLeft={overlay} />,
  );
  expect(map.flyTo).toHaveBeenCalledWith(expect.objectContaining({
    center: [128.53, 37.13],
    offset: [0, (288 + 48 + 24 - 64) / 2],
  }));
});

function ownedResizeObserver() {
  let callback: ResizeObserverCallback | undefined;
  const observe = vi.fn(), unobserve = vi.fn(), disconnect = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    constructor(next: ResizeObserverCallback) { callback = next; }
    observe = observe;
    unobserve = unobserve;
    disconnect = disconnect;
  });
  return { observe, disconnect, notify: () => callback?.([], {} as ResizeObserver) };
}

it('사용자 제스처 시작부터 늦은 패널 크기 변경이 시점을 되돌리지 않는다', () => {
  const resize = ownedResizeObserver();
  h.transportVisible = true;
  const map = fakeMap({ x: 72, y: 207 });
  h.map = map;
  const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
  const start = map.on.mock.calls.find(call => call[0] === 'movestart')?.[1];
  expect(start).toEqual(expect.any(Function));
  const fitted = map.fitBounds.mock.calls.length;
  act(() => {
    start({ originalEvent: new MouseEvent('mousedown') });
    resize.notify();
  });
  expect(map.fitBounds).toHaveBeenCalledTimes(fitted);
  view.unmount();
  expect(map.off).toHaveBeenCalledWith('movestart', start);
  expect(resize.disconnect).toHaveBeenCalled();
});

it('외곽 스택이 고정돼도 실제 패널 크기를 관찰하며 늦게 추가된 패널도 등록한다', async () => {
  const resize = ownedResizeObserver();
  h.transportVisible = false;
  h.map = fakeMap({ x: 72, y: 207 });
  const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
  h.transportVisible = true;
  await act(async () => {
    view.rerender(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    await Promise.resolve();
  });
  expect(resize.observe).toHaveBeenCalledWith(view.getByTestId('fit-panel'));
});

function setClientSize(element: Element, width: number, height: number) {
  Object.defineProperty(element, 'clientWidth', { configurable: true, value: width });
  Object.defineProperty(element, 'clientHeight', { configurable: true, value: height });
}

it('컨테이너가 자랐는데 maplibre가 아직 옛 크기면 맞추기 전에 resize한다(#686 NEAR-024)', () => {
  // 운영 데스크톱: 지도 컨테이너는 1590px로 자랐는데 maplibre transform은 ResizeObserver→rAF resize 전이라
  // 옛 높이다. 여백(DOM 상자 기준)이 옛 높이를 넘으면 fitBounds가 "cannot fit"으로 아무 일도 안 해 기본
  // 시점(127.5,36.5 z7)에 남는다. 맞춤은 항상 지금 컨테이너 크기의 transform에 대해 계산해야 한다.
  h.transportVisible = true;
  const map = fakeMap({ x: 300, y: 207 });
  setClientSize(map.getContainer(), 980, 1590);
  setClientSize(map.getCanvas(), 980, 360);
  h.map = map;
  render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);

  expect(map.resize).toHaveBeenCalled();
  expect(map.fitBounds).toHaveBeenCalled();
  expect(map.resize.mock.invocationCallOrder[0]!).toBeLessThan(
    map.fitBounds.mock.invocationCallOrder[0]!,
  );
});

it('크기가 같으면 맞춤 때 resize하지 않는다', () => {
  h.transportVisible = true;
  const map = fakeMap({ x: 300, y: 207 });
  setClientSize(map.getContainer(), 980, 900);
  setClientSize(map.getCanvas(), 980, 900);
  h.map = map;
  render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);

  expect(map.fitBounds).toHaveBeenCalled();
  expect(map.resize).not.toHaveBeenCalled();
});
