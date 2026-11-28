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
  mobile: true,
  // 내 위치 따라가기 대역 — 함수는 렌더마다 같은 참조(실제 훅의 useCallback처럼).
  following: false,
  isFollowing: () => h.following,
  notifyUserMove: vi.fn(),
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
  Marker: () => null,
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
// 지도 레이어 패널(교통) — 교통 레이어가 보일 때 맞춤이 피할 패널이다.
vi.mock('@/components/map/MapLayerControls', () => ({
  MapLayerControls: ({ transport }: { transport: { visible: boolean } | null }) =>
    transport?.visible ? <div data-map-fit-panel="" data-testid="fit-panel" /> : null,
}));
vi.mock('@/components/map/TransportMarkers', () => ({
  TransportMarkers: () => null,
  TransportMarkerLegend: () => null,
}));
vi.mock('@/components/map/TransportDetailDialog', () => ({ TransportDetailDialog: () => null }));
vi.mock('@/components/map/FeatureDetailModalController', () => ({
  FeatureDetailModalController: () => null,
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => h.mobile }));
vi.mock('@/components/map/MyLocationControl', () => ({
  useMyLocationControl: () => ({
    mode: h.following ? 'follow' : 'off',
    position: null,
    isFollowing: h.isFollowing,
    notifyUserMove: h.notifyUserMove,
  }),
  MyLocationControl: () => null,
}));

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
  h.mobile = true;
  h.following = false;
  h.notifyUserMove.mockReset();
});

describe('TripMapView 맞춤 배선', () => {
  it('낮은 지도에서도 맞춤·재맞춤·한 핀 flyTo가 검색 줄 clearance를 지킨다(#704 후속)', () => {
    RECTS['fit-container'] = box(0, 0, 390, 300);
    try {
      h.transportVisible = true;
      const map = fakeMap({ x: 72, y: 207 });
      h.map = map;
      const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
      // 1차는 검색 줄 아래(132)+원형 마커 21+간격 24, 패널 재맞춤은 패널 아래(288)+45가 60% 상한(180)에
      // 묶인다. 두 번 모두 아래 여백이 먼저 줄어든다.
      expect(map.fitBounds).toHaveBeenCalledTimes(2);
      expect(map.fitBounds.mock.calls.map((call) => call[1].padding.top)).toEqual([
        132 + 21 + 24,
        180,
      ]);
      for (const call of map.fitBounds.mock.calls) {
        expect(call[1].padding.bottom).toBeLessThan(64);
        expect(300 - call[1].padding.top - call[1].padding.bottom).toBeGreaterThan(0);
      }
      view.unmount();

      const single = fakeMap({ x: 500, y: 150 });
      h.map = single;
      h.transportVisible = false;
      render(<TripMapView points={[POINTS[0]!]} transportLayers overlayTopLeft={overlay} />);
      // 한 핀: 위·아래 차이의 절반만큼 내린다 — 0이면 핀이 검색 줄 밑 가운데에 남는다.
      expect(single.flyTo.mock.calls[0]?.[0].offset[1]).toBeGreaterThan(40);
    } finally {
      RECTS['fit-container'] = box(0, 0, 390, 700);
    }
  });

  it('교통 패널 밑에 북쪽 핀이 들면 패널 아래까지 한 번 더 맞춘다', () => {
    h.transportVisible = true;
    const map = fakeMap({ x: 72, y: 207 });
    h.map = map;
    render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);

    expect(map.fitBounds).toHaveBeenCalledTimes(2);
    // 1차: 검색 줄 아래(132) + 원형 마커 21 + 간격 24
    expect(map.fitBounds.mock.calls[0]?.[1].padding.top).toBe(132 + 21 + 24);
    // 2차: 패널 아래(288) + 원형 마커 21 + 간격 24
    expect(map.fitBounds.mock.calls[1]?.[1].padding.top).toBe(288 + 21 + 24);
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
    // (패널 아래 288 + 21 + 24) - 아래 여백 64, 절반
    expect(map.flyTo.mock.calls[0]?.[0].offset).toEqual([0, (288 + 21 + 24 - 64) / 2]);
  });

  it('장소가 하나라도 패널이 가운데 열 밖이면(데스크톱) 검색 줄만 기준으로 한다', () => {
    RECTS['fit-container'] = box(0, 0, 1000, 800);
    try {
      h.transportVisible = true;
      const map = fakeMap({ x: 500, y: 400 });
      h.map = map;
      render(<TripMapView points={[POINTS[0]!]} transportLayers overlayTopLeft={overlay} />);

      expect(map.flyTo.mock.calls[0]?.[0].offset).toEqual([0, (132 + 21 + 24 - 64) / 2]);
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
    expect(map.fitBounds.mock.calls[2]?.[1].padding.top).toBe(288 + 21 + 24);

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

it('제어된 POI popup이 native로 닫히면 선택 해제를 소유자에게 전달한다(데스크톱)', () => {
  h.mobile = false;
  h.map = fakeMap({ x: 300, y: 300 });
  const select = vi.fn();
  render(<TripMapView points={POINTS} selectedPoiId="north" onSelectPoi={select} />);
  expect(h.popupClose).toEqual(expect.any(Function));
  h.popupClose!();
  expect(select).toHaveBeenCalledWith(null);
});

it('모바일은 선택한 장소의 이름 팝업을 띄우지 않는다 — 이름은 마커 라벨이 이미 보여 준다(이중 표시)', () => {
  h.map = fakeMap({ x: 300, y: 300 });
  render(<TripMapView points={POINTS} selectedPoiId="north" onSelectPoi={vi.fn()} />);
  expect(h.popupClose).toBeNull();
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
    offset: [0, (288 + 21 + 24 - 64) / 2],
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

describe('TripMapView와 내 위치 따라가기(2026-11-28 "dmz 자생" 보고 후속)', () => {
  it('따라가는 동안에는 장소 목록이 바뀌거나 패널 크기가 바뀌어도 다시 맞추지 않고 따라가기도 끄지 않는다', () => {
    const resize = ownedResizeObserver();
    h.transportVisible = true;
    const map = fakeMap({ x: 72, y: 207 });
    h.map = map;
    const view = render(<TripMapView points={POINTS} transportLayers overlayTopLeft={overlay} />);
    const fitted = map.fitBounds.mock.calls.length;
    map.flyTo.mockClear();

    h.following = true;
    // TripDetail의 mapPoints는 여행을 다시 받으면 새 참조가 된다(같은 장소여도).
    view.rerender(
      <TripMapView points={[...POINTS]} transportLayers overlayTopLeft={overlay} />,
    );
    act(() => resize.notify());
    expect(map.fitBounds).toHaveBeenCalledTimes(fitted);
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(h.notifyUserMove).not.toHaveBeenCalled();

    // 따라가기를 끄면 다음 맞춤 계기(장소 목록 변경)부터 다시 맞춘다.
    h.following = false;
    view.rerender(<TripMapView points={[POINTS[1]!, POINTS[0]!]} transportLayers overlayTopLeft={overlay} />);
    expect(map.fitBounds.mock.calls.length).toBeGreaterThan(fitted);
  });

  it('목록에서 장소를 고르면 알리고 옮긴다 — 같은 선택에서 목록만 다시 받으면 따라가는 동안 옮기지 않는다', () => {
    const map = fakeMap({ x: 300, y: 300 });
    h.map = map;
    h.following = true;
    const view = render(<TripMapView points={POINTS} overlayTopLeft={overlay} />);
    map.flyTo.mockClear();

    view.rerender(<TripMapView points={POINTS} selectedPoiId="north" overlayTopLeft={overlay} />);
    expect(h.notifyUserMove).toHaveBeenCalledTimes(1);
    expect(map.flyTo).toHaveBeenCalledTimes(1);
    expect(h.notifyUserMove.mock.invocationCallOrder[0]!).toBeLessThan(
      map.flyTo.mock.invocationCallOrder[0]!,
    );

    // 여행을 다시 받아 selected 참조만 바뀐다 — 사용자 선택이 아니다.
    view.rerender(
      <TripMapView points={[...POINTS]} selectedPoiId="north" overlayTopLeft={overlay} />,
    );
    expect(h.notifyUserMove).toHaveBeenCalledTimes(1);
    expect(map.flyTo).toHaveBeenCalledTimes(1);

    // 같은 장소라도 다시 누르면(focusRequest) 고른 이동이다.
    view.rerender(
      <TripMapView points={POINTS} selectedPoiId="north" focusRequest={1} overlayTopLeft={overlay} />,
    );
    expect(h.notifyUserMove).toHaveBeenCalledTimes(2);
    expect(map.flyTo).toHaveBeenCalledTimes(2);

    // 선택을 풀었다가 같은 장소를 다시 고르는 것도 고른 이동이다.
    view.rerender(<TripMapView points={POINTS} focusRequest={1} overlayTopLeft={overlay} />);
    view.rerender(
      <TripMapView points={POINTS} selectedPoiId="north" focusRequest={1} overlayTopLeft={overlay} />,
    );
    expect(h.notifyUserMove).toHaveBeenCalledTimes(3);
    expect(map.flyTo).toHaveBeenCalledTimes(3);
  });

  it('일자를 숨겼다 다시 보여 고른 장소가 목록에서 잠깐 빠졌다 돌아와도 고른 이동으로 보지 않는다', () => {
    const map = fakeMap({ x: 300, y: 300 });
    h.map = map;
    h.following = true;
    const view = render(<TripMapView points={POINTS} overlayTopLeft={overlay} />);
    view.rerender(<TripMapView points={POINTS} selectedPoiId="north" overlayTopLeft={overlay} />);
    expect(h.notifyUserMove).toHaveBeenCalledTimes(1);
    map.flyTo.mockClear();

    // 선택 id는 그대로, 지도 목록에서만 빠진다(일자 숨김) → 다시 보인다(일자 재표시).
    view.rerender(
      <TripMapView points={[POINTS[1]!]} selectedPoiId="north" overlayTopLeft={overlay} />,
    );
    view.rerender(<TripMapView points={POINTS} selectedPoiId="north" overlayTopLeft={overlay} />);
    expect(h.notifyUserMove).toHaveBeenCalledTimes(1);
    expect(map.flyTo).not.toHaveBeenCalled();
  });
});
