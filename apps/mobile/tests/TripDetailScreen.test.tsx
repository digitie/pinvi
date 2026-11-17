import { useImperativeHandle } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlatformMarkerItem, PlatformVWorldMapProps } from '../components/VWorldMap.types';

/**
 * 여행 상세 화면 — 네이티브 지도(`vworld-map-rn`)는 mock으로 바꾸고, 화면이 지도에 넘기는 마커·첫 시점·
 * 카메라 명령과 목록 연동을 본다. 실제 지도 렌더링은 기기(EAS dev client)와 Expo Web 산출물에서 확인한다.
 */

const map = vi.hoisted(() => ({
  props: null as PlatformVWorldMapProps | null,
  flyTo: vi.fn(),
  fitBounds: vi.fn(),
  mounts: 0,
}));

vi.mock('../components/VWorldMap', () => ({
  VWorldMapView: (props: PlatformVWorldMapProps) => {
    map.props = props;
    useImperativeHandle(
      props.ref,
      () => {
        map.mounts += 1;
        return { flyTo: map.flyTo, fitBounds: map.fitBounds, zoomTo: vi.fn() };
      },
      [],
    );
    return (
      <div data-testid="vworld-map">
        {(props.markers ?? []).map((marker) => (
          <button
            key={marker.id}
            type="button"
            data-marker-id={marker.id}
            aria-label={`marker ${marker.label ?? marker.ariaLabel ?? marker.id}`}
            onClick={() => props.onFeaturePress?.(marker)}
          />
        ))}
      </div>
    );
  },
}));

vi.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ tripId: 'trip-1' }),
  useRouter: () => ({ push: vi.fn() }),
}));

const server = vi.hoisted(() => ({
  paths: [] as string[],
  transportEnabled: true,
}));

function poi(id: string, title: string, coord: { lon: number; lat: number } | null, color: string) {
  return {
    poi_id: id,
    feature_id: coord ? `feature-${id}` : null,
    sort_order: id,
    title,
    feature: coord ? { coord } : {},
    marker_color: null,
    marker_icon: null,
    display_marker_color: color,
    feature_resolution_state: coord ? 'found' : 'not_linked',
    user_note: null,
  };
}

function day(index: number, pois: ReturnType<typeof poi>[]) {
  return {
    day_index: index,
    title: null,
    date: null,
    effective_date: null,
    out_of_range: false,
    marker_color: null,
    holidays: [],
    rise_set: null,
    rise_set_reference: null,
    pois,
  };
}

const TRIP_VIEW = {
  trip: {
    trip_id: 'trip-1',
    title: '강릉 여행',
    start_date: '2026-11-20',
    end_date: '2026-11-21',
    description: null,
    status: 'planned',
  },
  days: [
    day(1, [
      poi('poi-a', '경포대', { lon: 128.9, lat: 37.8 }, 'P-01'),
      poi('poi-b', '안목해변', { lon: 128.95, lat: 37.77 }, 'P-02'),
    ]),
    day(2, [
      poi('poi-c', '오죽헌', { lon: 128.88, lat: 37.78 }, 'P-05'),
      poi('poi-d', '좌표 없는 메모', null, 'P-05'),
    ]),
  ],
  share_links: [],
  broken_feature_count: 0,
};

vi.mock('../lib/api', () => ({
  api: {
    trips: {
      get: async () => TRIP_VIEW,
      createShareToken: vi.fn(),
      revokeShareToken: vi.fn(),
    },
  },
  apiClient: {
    request: async (path: string) => {
      server.paths.push(path);
      if (path === '/mobile/vworld/token') {
        return { api_key: 'test-key', key_source: 'server-issued', ttl_seconds: 60 };
      }
      if (path === '/transport/status') {
        return {
          enabled: server.transportEnabled,
          layers: [
            { layer: 'fuel_station', available: true },
            { layer: 'highway_incident', available: true },
          ],
        };
      }
      if (path.startsWith('/transport/markers-near')) {
        return {
          radius_m: { fuel_station: 10_000, highway_incident: 20_000 },
          layers: [
            {
              layer: 'fuel_station',
              status: 'ok',
              truncated: false,
              items: [
                {
                  layer: 'fuel_station',
                  feature_id: 'fuel-1',
                  name: '강릉 주유소',
                  coord: { lon: 128.91, lat: 37.79 },
                  address: { road: '강릉시 어딘가', jibun: null },
                  marker_color: null,
                  marker_icon: null,
                  category: null,
                  prices: [],
                },
              ],
            },
          ],
        };
      }
      throw new Error(`unexpected ${path}`);
    },
  },
}));

const { default: TripDetailScreen } = await import('../app/(app)/trips/[tripId]/index');

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TripDetailScreen />
    </QueryClientProvider>,
  );
}

const markers = (): PlatformMarkerItem[] => map.props?.markers ?? [];
const nearRequests = () => server.paths.filter((p) => p.startsWith('/transport/markers-near'));

beforeEach(() => {
  map.props = null;
  map.flyTo.mockReset();
  map.fitBounds.mockReset();
  map.mounts = 0;
  server.paths = [];
  server.transportEnabled = true;
});

describe('모바일 여행 상세 지도', () => {
  it('좌표 있는 여행 장소를 일자·마커 색 + 이름 라벨 마커로 그리고, 모두 담는 시점으로 연다', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    const poiMarkers = markers().filter((m) => m.id.startsWith('poi:'));
    expect(poiMarkers.map((m) => [m.id, m.label, m.color])).toEqual([
      ['poi:poi-a', '경포대', '#E53935'],
      ['poi:poi-b', '안목해변', '#FB8C00'],
      ['poi:poi-c', '오죽헌', '#43A047'],
    ]);
    // 첫 시점은 세 장소의 가운데 근처(위 여백 때문에 조금 북쪽).
    const [lon, lat] = map.props?.initialCenter ?? [0, 0];
    expect(lon).toBeGreaterThan(128.88);
    expect(lon).toBeLessThan(128.95);
    expect(lat).toBeGreaterThan(37.77);
    expect(lat).toBeLessThan(37.85);
    expect(map.props?.initialZoom).toBeGreaterThan(10);
    // 좌표 없는 장소는 목록에만 있고 안내가 붙는다.
    expect(screen.getByText('좌표가 없어 지도에 표시하지 않습니다.')).toBeTruthy();
  });

  it('목록에서 장소를 누르면 그 줄을 고르고 지도를 그 장소로 옮긴다(같은 장소를 다시 눌러도)', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    const row = screen.getByTestId('trip-poi-row-poi-b');
    fireEvent.click(row);
    await waitFor(() =>
      expect(map.flyTo).toHaveBeenLastCalledWith({ center: [128.95, 37.77], zoom: 14 }),
    );
    expect(row.getAttribute('aria-selected')).toBe('true');
    expect(markers().find((m) => m.id === 'poi:poi-b')?.selected).toBe(true);

    fireEvent.click(row);
    await waitFor(() => expect(map.flyTo).toHaveBeenCalledTimes(2));
  });

  it('지도에서 장소 마커를 누르면 목록의 그 줄이 강조된다', async () => {
    renderScreen();
    const marker = await screen.findByRole('button', { name: 'marker 오죽헌' });
    fireEvent.click(marker);
    await waitFor(() =>
      expect(screen.getByTestId('trip-poi-row-poi-c').getAttribute('aria-selected')).toBe('true'),
    );
    expect(screen.getByTestId('trip-poi-row-poi-a').getAttribute('aria-selected')).toBe('false');
    // 지도 쪽 선택은 지도를 옮기지 않는다(사용자가 보고 있는 시점 유지).
    expect(map.flyTo).not.toHaveBeenCalled();
  });

  it('지도를 접으면 지도를 내리고, 접힌 채 목록에서 고르면 그 장소를 가운데로 펼친다', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    fireEvent.click(screen.getByRole('button', { name: '지도 접기' }));
    expect(screen.queryByTestId('vworld-map')).toBeNull();

    fireEvent.click(screen.getByTestId('trip-poi-row-poi-a'));
    await screen.findByTestId('vworld-map');
    expect(map.props?.initialCenter).toEqual([128.9, 37.8]);
    expect(map.props?.initialZoom).toBe(14);
    // 펼치며 연 시점이 이미 그 장소다 — 같은 요청으로 한 번 더 옮기지 않는다.
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '지도 접기' })).toBeTruthy();
  });

  it('전체 보기는 모든 장소를 여백을 두고 fitBounds로 다시 담는다', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    fireEvent.click(screen.getByRole('button', { name: '전체 보기' }));
    expect(map.flyTo).not.toHaveBeenCalled();
    expect(map.fitBounds).toHaveBeenCalledTimes(1);
    const [bounds, options] = map.fitBounds.mock.calls[0]! as [
      { sw: [number, number]; ne: [number, number] },
      { paddingPx: { top: number; right: number; bottom: number; left: number } },
    ];
    expect(bounds).toEqual({ sw: [128.88, 37.77], ne: [128.95, 37.8] });
    // 이름 라벨이 원 아래·옆으로 퍼지므로 옆·아래 여백을 둔다(칩 줄이 덮으면 위도).
    expect(options.paddingPx.left).toBeGreaterThan(0);
    expect(options.paddingPx.bottom).toBeGreaterThan(0);
  });

  it('교통 칩(반경 모드)을 켜면 여행 장소 좌표로 조회하고 마커·반경 상태 줄을 보인다', async () => {
    renderScreen();
    const chip = await screen.findByRole('button', { name: '주유소' });
    expect(screen.getByRole('button', { name: '교통 돌발' })).toBeTruthy();
    expect(nearRequests()).toEqual([]);

    fireEvent.click(chip);
    await waitFor(() => expect(nearRequests()).toHaveLength(1));
    const query = new URL(nearRequests()[0]!, 'http://x').searchParams;
    expect(query.get('points')).toBe('128.90000,37.80000;128.95000,37.77000;128.88000,37.78000');
    expect(query.get('layers')).toBe('fuel_station');

    const status = await screen.findByTestId('trip-transport-status');
    await waitFor(() =>
      expect(within(status).getByText(/주유소 · 1곳 · 여행 장소 10km 이내/)).toBeTruthy(),
    );
    await waitFor(() =>
      expect(markers().map((m) => m.id)).toContain('transport:fuel_station:fuel-1'),
    );

    // 교통 마커를 누르면 카드가 열린다(여행 장소 선택은 바뀌지 않는다).
    fireEvent.click(screen.getByRole('button', { name: 'marker 강릉 주유소' }));
    expect(await screen.findByText('강릉시 어딘가')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByText('강릉시 어딘가')).toBeNull());
  });

  it('교통 기능이 꺼져 있으면 칩도 반경 조회도 없다', async () => {
    server.transportEnabled = false;
    renderScreen();
    await screen.findByTestId('vworld-map');
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(screen.queryByRole('button', { name: '주유소' })).toBeNull();
    expect(nearRequests()).toEqual([]);
  });
});
