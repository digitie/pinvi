import { Fragment, useEffect, type ReactNode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PlaceSearchResult } from '@pinvi/schemas';

// 탐색 지도 배선(2026-11-28 "dmz 자생" 보고, PR #816): 사용자가 고른 카메라 이동(검색 결과 선택·서버 묶음
// 마커·"여기서 주변 보기")은 옮기기 **직전에** 내 위치 따라가기에 알려야 한다 — 그래야 다음 위치 갱신이 지도를
// 내 위치로 되돌리지 않는다. CI에는 VWorld 키가 없어 지도를 대역으로 세운다.

const h = vi.hoisted(() => ({
  map: null as unknown,
  onContextMenu: null as ((event: unknown) => void) | null,
  onSearchSelect: null as ((result: unknown) => void) | null,
  notifyUserMove: vi.fn(),
}));

vi.mock('@/components/map/vworldPrimitives', () => ({
  VWorldMap: ({
    onLoad,
    onContextMenu,
    children,
  }: {
    onLoad?: (map: unknown) => void;
    onContextMenu?: (event: unknown) => void;
    children?: ReactNode;
  }) => {
    h.onContextMenu = onContextMenu ?? null;
    useEffect(() => {
      onLoad?.(h.map);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return <div>{children}</div>;
  },
  ClusterLayer: ({
    points,
    renderMarker,
  }: {
    points: { id: string }[];
    renderMarker: (point: unknown) => ReactNode;
  }) => (
    <>
      {points.map((point) => (
        <Fragment key={point.id}>{renderMarker(point)}</Fragment>
      ))}
    </>
  ),
  MakiMarker: ({ ariaLabel, onClick }: { ariaLabel?: string; onClick?: () => void }) => (
    <button type="button" aria-label={ariaLabel} onClick={onClick} />
  ),
  MapContextMenu: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  MapFallback: () => null,
  MapLoadingSkeleton: () => null,
  Popup: () => null,
  UserLocationMarker: () => null,
  WeatherMarker: () => null,
}));
vi.mock('@/components/map/MapSearchBox', () => ({
  MapSearchBox: ({ onSelect }: { onSelect: (result: unknown) => void }) => {
    h.onSearchSelect = onSelect;
    return null;
  },
}));
vi.mock('@/components/map/MyLocationControl', () => ({
  useMyLocationControl: () => ({
    mode: 'follow',
    position: null,
    notifyUserMove: h.notifyUserMove,
  }),
  MyLocationControl: () => null,
}));
vi.mock('@/components/map/ExploreFeatureMarker', () => ({
  EXPLORE_MARKER_SIZE: 22,
  ExploreFeatureMarker: () => null,
}));
vi.mock('@/components/map/MapLayerControls', () => ({ MapLayerControls: () => null }));
vi.mock('@/components/map/TransportMarkers', () => ({
  TransportMarkers: () => null,
  TransportMarkerLegend: () => null,
}));
vi.mock('@/components/map/TransportDetailDialog', () => ({ TransportDetailDialog: () => null }));
vi.mock('@/components/map/FeatureDetailModalController', () => ({
  FeatureDetailModalController: () => null,
}));
vi.mock('@/components/map/FeatureRequestDialog', () => ({ FeatureRequestDialog: () => null }));
vi.mock('@/lib/useTransportLayers', () => ({
  useTransportLayers: () => ({
    visible: false,
    onViewportChange: () => {},
    openDetail: () => {},
    closeDetail: () => {},
    points: [],
    selectedId: null,
    detail: null,
  }),
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => false }));
vi.mock('@/lib/useFeatureDetailCard', () => ({
  useFeatureDetailCard: () => ({ card: null, loading: false, error: null }),
}));
vi.mock('@/lib/useAbortableLoad', () => ({ useAbortableLoad: () => {} }));
vi.mock('@/lib/popupClearance', () => ({ usePopupClearOfOverlays: () => {} }));
// 자동 센터링은 권한이 없어 바로 끝난다 — 그 뒤 화면 범위 조회가 열린다.
vi.mock('@/lib/locationAdapter', () => ({
  webLocationAdapter: { getPermissionState: async () => 'denied' },
}));
vi.mock('@/lib/locationConsent', () => ({ getLocationConsentState: async () => 'missing' }));
vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  return {
    ...actual,
    featureApi: () => ({
      inBounds: async () => ({
        items: [],
        clusters: [{ cluster_key: 'c-1', coord: { lon: 127.2, lat: 37.7 }, feature_count: 12 }],
        cluster_unit: 'grid',
        zoom: 9,
        bbox: { lng_min: 126.5, lat_min: 37.0, lng_max: 127.5, lat_max: 38.0 },
      }),
      weather: async () => null,
    }),
    weatherApi: () => ({
      markersInBounds: async () => ({
        items: [],
        zoom: 9,
        bbox: { lng_min: 126.5, lat_min: 37.0, lng_max: 127.5, lat_max: 38.0 },
      }),
    }),
  };
});

import { FeatureMapView } from '@/components/map/FeatureMapView';

function fakeMap() {
  return {
    getZoom: () => 9,
    getBounds: () => ({
      getWest: () => 126.5,
      getSouth: () => 37.0,
      getEast: () => 127.5,
      getNorth: () => 38.0,
    }),
    getContainer: () => document.createElement('div'),
    flyTo: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  };
}

function expectNotifiedBeforeFly(map: ReturnType<typeof fakeMap>) {
  expect(h.notifyUserMove).toHaveBeenCalledTimes(1);
  expect(map.flyTo).toHaveBeenCalledTimes(1);
  expect(h.notifyUserMove.mock.invocationCallOrder[0]!).toBeLessThan(
    map.flyTo.mock.invocationCallOrder[0]!,
  );
}

/** 렌더 뒤 자동 센터링·화면 범위 조회가 끝날 때까지 기다린다(묶음 마커가 보이면 끝). */
async function renderSettled() {
  render(<FeatureMapView apiKey="test" />);
  return waitFor(() => screen.getByRole('button', { name: '12곳' }));
}

afterEach(() => {
  h.notifyUserMove.mockReset();
  h.onContextMenu = null;
  h.onSearchSelect = null;
});

describe('FeatureMapView — 사용자가 고른 이동은 옮기기 직전에 따라가기에 알린다', () => {
  it('검색 결과 선택', async () => {
    const map = fakeMap();
    h.map = map;
    await renderSettled();
    const dmz = {
      source: 'feature',
      name: 'DMZ자생식물원',
      coord: { lon: 128.1306, lat: 38.2797 },
      feature_id: 'feat-dmz-garden',
      category: 'garden',
      marker_color: 'P-07',
      marker_icon: 'garden',
    } as unknown as PlaceSearchResult;
    act(() => h.onSearchSelect?.(dmz));
    expectNotifiedBeforeFly(map);
    expect(map.flyTo).toHaveBeenCalledWith({ center: [128.1306, 38.2797], zoom: 15 });
  });

  it('좌표 없는 검색 결과(상세만 연다)는 지도를 옮기지 않으므로 알리지 않는다', async () => {
    const map = fakeMap();
    h.map = map;
    await renderSettled();
    act(() =>
      h.onSearchSelect?.({ source: 'feature', name: '좌표 없음', coord: null, feature_id: 'f-x' }),
    );
    expect(h.notifyUserMove).not.toHaveBeenCalled();
    expect(map.flyTo).not.toHaveBeenCalled();
  });

  it('서버 묶음 마커', async () => {
    const map = fakeMap();
    h.map = map;
    const cluster = await renderSettled();
    fireEvent.click(cluster);
    expectNotifiedBeforeFly(map);
    expect(map.flyTo).toHaveBeenCalledWith({ center: [127.2, 37.7], zoom: 11 });
  });

  it('"여기서 주변 보기"', async () => {
    const map = fakeMap();
    h.map = map;
    await renderSettled();
    act(() =>
      h.onContextMenu?.({
        originalEvent: { clientX: 10, clientY: 20 },
        lngLat: { lng: 127.05, lat: 37.55 },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: '여기서 주변 보기' }));
    expectNotifiedBeforeFly(map);
    expect(map.flyTo).toHaveBeenCalledWith({ center: [127.05, 37.55], zoom: 15 });
  });
});
