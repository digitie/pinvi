import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TransportLayer } from '@pinvi/schemas';

type Responder = (layers: TransportLayer[]) => unknown;

const api = vi.hoisted(() => ({
  paths: [] as string[],
  statusEnabled: true,
  near: null as null | ((layers: string[]) => unknown),
}));

vi.mock('../lib/api', () => ({
  apiClient: {
    request: async (path: string) => {
      api.paths.push(path);
      if (path === '/transport/status') {
        return {
          enabled: api.statusEnabled,
          layers: [
            { layer: 'fuel_station', available: true },
            { layer: 'highway_incident', available: true },
          ],
        };
      }
      if (path.startsWith('/transport/markers-near')) {
        const layers = new URL(path, 'http://x').searchParams.get('layers')?.split(',') ?? [];
        if (!api.near) throw new Error('no responder');
        return api.near(layers);
      }
      throw new Error(`unexpected ${path}`);
    },
  },
}));

const { useTripTransport, TRIP_TRANSPORT_DEBOUNCE_MS } = await import('../lib/useTripTransport');

const FUEL_ITEM = {
  layer: 'fuel_station',
  feature_id: 'fuel-1',
  name: '가 주유소',
  coord: { lon: 127.01, lat: 37.51 },
  address: { road: null, jibun: null },
  marker_color: null,
  marker_icon: null,
  category: null,
  prices: [],
};

const okEverything: Responder = (layers) => ({
  radius_m: { fuel_station: 10_000, highway_incident: 20_000 },
  layers: layers.map((layer) => ({
    layer,
    status: 'ok',
    truncated: false,
    items: layer === 'fuel_station' ? [FUEL_ITEM] : [],
  })),
});

const POINTS = [
  { lon: 127, lat: 37.5 },
  { lon: 127.2, lat: 37.6 },
];

const nearRequests = () => api.paths.filter((p) => p.startsWith('/transport/markers-near'));

function setup(initial: { active?: boolean; points?: { lon: number; lat: number }[] } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(
    (props: { active: boolean; points: { lon: number; lat: number }[] }) => useTripTransport(props),
    { wrapper, initialProps: { active: initial.active ?? true, points: initial.points ?? POINTS } },
  );
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

beforeEach(() => {
  api.paths = [];
  api.statusEnabled = true;
  api.near = okEverything as (layers: string[]) => unknown;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useTripTransport — 여행 장소 반경 조회 규칙', () => {
  it('켜기 전에는 조회하지 않고, 켜면 디바운스 뒤 여행 장소 좌표·켠 레이어로 한 번 조회한다', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(nearRequests()).toEqual([]);

    act(() => result.current.toggle('fuel_station'));
    // 디바운스 동안은 조회하지 않는다.
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS / 2);
    expect(nearRequests()).toEqual([]);

    await waitFor(() => expect(nearRequests()).toHaveLength(1));
    const query = new URL(nearRequests()[0]!, 'http://x').searchParams;
    expect(query.get('points')).toBe('127.00000,37.50000;127.20000,37.60000');
    expect(query.get('layers')).toBe('fuel_station');
    expect(query.get('limit')).toBe('200');
    await waitFor(() => expect(result.current.markers).toHaveLength(1));
    expect(result.current.markers[0]).toMatchObject({
      id: 'transport:fuel_station:fuel-1',
      coordinate: [127.01, 37.51],
    });
    expect(result.current.radiusM).toEqual({ fuel_station: 10_000, highway_incident: 20_000 });
  });

  it('연달아 누르면 마지막 상태로 한 번만 조회한다', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('fuel_station'));
    act(() => result.current.toggle('highway_incident'));
    await waitFor(() => expect(nearRequests()).toHaveLength(1));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(nearRequests()).toHaveLength(1);
    expect(new URL(nearRequests()[0]!, 'http://x').searchParams.get('layers')).toBe(
      'fuel_station,highway_incident',
    );
  });

  it('새 배열이어도 5자리 좌표가 같으면 다시 조회하지 않고, 좌표가 바뀌면 다시 조회한다', async () => {
    const { result, rerender } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('fuel_station'));
    await waitFor(() => expect(nearRequests()).toHaveLength(1));

    rerender({
      active: true,
      points: [
        { lon: 127.0000001, lat: 37.5000001 },
        { lon: 127.2, lat: 37.6 },
        // 같은 자리 중복은 한 번만 보낸다.
        { lon: 127, lat: 37.5 },
      ],
    });
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(nearRequests()).toHaveLength(1);

    rerender({ active: true, points: [{ lon: 128, lat: 35.1 }] });
    await waitFor(() => expect(nearRequests()).toHaveLength(2));
    expect(new URL(nearRequests()[1]!, 'http://x').searchParams.get('points')).toBe(
      '128.00000,35.10000',
    );
  });

  it('같은 장소·레이어 조합은 60초 동안 다시 조회하지 않는다', async () => {
    const { result } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('fuel_station'));
    await waitFor(() => expect(nearRequests()).toHaveLength(1));
    await waitFor(() => expect(result.current.results).toHaveLength(1));

    // 껐다 켜도 캐시에서 바로 그린다.
    act(() => result.current.toggle('fuel_station'));
    await waitFor(() => expect(result.current.results).toEqual([]));
    act(() => result.current.toggle('fuel_station'));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(nearRequests()).toHaveLength(1);
    expect(result.current.results.map((r) => r.layer)).toEqual(['fuel_station']);

    // 60초가 지나면 같은 조합도 다시 조회한다.
    const realNow = Date.now.bind(Date);
    vi.spyOn(Date, 'now').mockImplementation(() => realNow() + 61_000);
    act(() => result.current.toggle('fuel_station'));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    act(() => result.current.toggle('fuel_station'));
    await waitFor(() => expect(nearRequests()).toHaveLength(2));
  });

  it('요청한 레이어가 응답에 없으면 불러올 수 없음으로 채운다', async () => {
    api.near = ((layers: string[]) => ({
      radius_m: { fuel_station: 10_000 },
      layers: layers
        .filter((layer) => layer === 'fuel_station')
        .map((layer) => ({ layer, status: 'ok', truncated: false, items: [] })),
    })) as (layers: string[]) => unknown;
    const { result } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('fuel_station'));
    act(() => result.current.toggle('highway_incident'));
    await waitFor(() => expect(result.current.results).toHaveLength(2));
    expect(result.current.results.map((r) => [r.layer, r.status])).toEqual([
      ['fuel_station', 'ok'],
      ['highway_incident', 'unavailable'],
    ]);
  });

  it('요청이 실패하면 켠 레이어를 모두 불러올 수 없음으로 보인다', async () => {
    api.near = () => {
      throw new Error('boom');
    };
    const { result } = setup();
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('highway_incident'));
    await waitFor(() => expect(result.current.results).toHaveLength(1));
    expect(result.current.results[0]).toMatchObject({
      layer: 'highway_incident',
      status: 'unavailable',
    });
    expect(result.current.markers).toEqual([]);
  });

  it('기능이 꺼져 있으면 숨기고, 비활성(비로그인 화면)이면 상태조차 조회하지 않는다', async () => {
    api.statusEnabled = false;
    const off = setup();
    await waitFor(() => expect(api.paths).toContain('/transport/status'));
    act(() => off.result.current.toggle('fuel_station'));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(off.result.current.visible).toBe(false);
    expect(nearRequests()).toEqual([]);
    off.unmount();

    api.paths = [];
    const inactive = setup({ active: false });
    act(() => inactive.result.current.toggle('fuel_station'));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(inactive.result.current.visible).toBe(false);
    expect(api.paths).toEqual([]);
  });

  it('여행 장소에 좌표가 없으면 조회하지 않는다', async () => {
    const { result } = setup({ points: [] });
    await waitFor(() => expect(result.current.visible).toBe(true));
    act(() => result.current.toggle('fuel_station'));
    await sleep(TRIP_TRANSPORT_DEBOUNCE_MS + 50);
    expect(nearRequests()).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
