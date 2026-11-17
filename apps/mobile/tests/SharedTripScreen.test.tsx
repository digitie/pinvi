import { useImperativeHandle } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlatformMarkerItem, PlatformVWorldMapProps } from '../components/VWorldMap.types';
import { rainyDayCard } from './fixtures/weather';

/** 로그인 없는 공유 화면 — 지도(공유 토큰 범위 키)·마커·목록 연동, 교통·장소별 날씨 요청 없음. */

const map = vi.hoisted(() => ({
  props: null as PlatformVWorldMapProps | null,
  flyTo: vi.fn(),
}));

vi.mock('../components/VWorldMap', () => ({
  VWorldMapView: (props: PlatformVWorldMapProps) => {
    map.props = props;
    useImperativeHandle(
      props.ref,
      () => ({ flyTo: map.flyTo, fitBounds: vi.fn(), zoomTo: vi.fn() }),
      [],
    );
    return (
      <div data-testid="vworld-map">
        {(props.markers ?? []).map((marker) => (
          <button
            key={marker.id}
            type="button"
            aria-label={`marker ${marker.label ?? marker.id}`}
            onClick={() => props.onFeaturePress?.(marker)}
          />
        ))}
      </div>
    );
  },
}));

vi.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ tripId: 'trip-1', token: 'tok-1' }),
}));

const server = vi.hoisted(() => ({ paths: [] as string[], keyStatus: 200 }));

function poi(id: string, title: string, coord: { lon: number; lat: number } | null) {
  return {
    poi_id: id,
    feature_id: coord ? `feature-${id}` : null,
    title,
    feature: coord ? { coord } : {},
    marker_color: null,
    marker_icon: 'cafe',
    display_marker_color: 'P-02',
    feature_resolution_state: coord ? 'found' : 'not_linked',
    user_note: '비공개 메모',
  };
}

const SHARED = {
  visibility: 'view_only',
  trip: {
    trip_id: 'trip-1',
    title: '공유된 강릉',
    start_date: null,
    end_date: null,
    description: null,
  },
  days: [
    {
      day_index: 1,
      title: null,
      date: null,
      effective_date: null,
      out_of_range: false,
      marker_color: null,
      holidays: [],
      rise_set: null,
      rise_set_reference: null,
      weather_cards: { c1: rainyDayCard() },
      weather_by_feature_id: { 'feature-poi-a': { state: 'found', card_key: 'c1' } },
      pois: [
        poi('poi-a', '경포대', { lon: 128.9, lat: 37.8 }),
        poi('poi-b', '안목해변', { lon: 128.95, lat: 37.77 }),
        poi('poi-c', '좌표 없음', null),
      ],
    },
  ],
  broken_feature_count: 0,
};

vi.mock('../lib/api', () => ({
  api: { trips: { getShared: async () => SHARED } },
  apiClient: {
    request: async (path: string) => {
      server.paths.push(path);
      if (path === '/mobile/shared/trip-1/tok-1/vworld/token') {
        if (server.keyStatus !== 200) throw new Error('404');
        return { api_key: 'shared-key', key_source: 'server-issued', ttl_seconds: 60 };
      }
      throw new Error(`unexpected ${path}`);
    },
  },
}));

const { default: SharedTripScreen } = await import('../app/shared/[tripId]/[token]');

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SharedTripScreen />
    </QueryClientProvider>,
  );
}

const markers = (): PlatformMarkerItem[] => map.props?.markers ?? [];

beforeEach(() => {
  map.props = null;
  map.flyTo.mockReset();
  server.paths = [];
  server.keyStatus = 200;
});

describe('모바일 공유 화면 지도', () => {
  it('공유 토큰 범위 키로 지도를 띄우고 장소를 아이콘·이름·일자 날씨 마커로 그린다', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    expect(map.props?.apiKey).toBe('shared-key');
    expect(markers().map((m) => [m.id, m.label, m.icon])).toEqual([
      ['poi:poi-a', '경포대', 'cafe'],
      ['poi:poi-b', '안목해변', 'cafe'],
    ]);
    await waitFor(() =>
      expect(markers().find((m) => m.id === 'poi:poi-a')?.weather).toMatchObject({
        condition: 'rain',
      }),
    );
    // 로그인 키·교통·장소별 날씨는 부르지 않는다(공유 화면에는 교통 칩이 없다 — NEAR-027).
    expect(server.paths).toEqual(['/mobile/shared/trip-1/tok-1/vworld/token']);
    expect(screen.queryByRole('button', { name: '주유소' })).toBeNull();
    expect(screen.queryByTestId('weather-badge')).toBeNull();
    // 공유 화면은 메모를 보이지 않는다(기존 화면과 같다).
    expect(screen.queryByText('비공개 메모')).toBeNull();
  });

  it('목록 ↔ 지도: 줄을 누르면 그 장소로, 마커를 누르면 그 줄이 강조된다', async () => {
    renderScreen();
    await screen.findByTestId('vworld-map');
    fireEvent.click(screen.getByTestId('trip-poi-row-poi-b'));
    await waitFor(() =>
      expect(map.flyTo).toHaveBeenLastCalledWith({ center: [128.95, 37.77], zoom: 14 }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'marker 경포대' }));
    await waitFor(() =>
      expect(screen.getByTestId('trip-poi-row-poi-a').getAttribute('aria-selected')).toBe('true'),
    );
  });

  it('키를 못 받으면 지도 자리에 안내만, 일정은 그대로 보인다', async () => {
    server.keyStatus = 404;
    renderScreen();
    expect(await screen.findByText(/지도를 불러올 수 없습니다/)).toBeTruthy();
    expect(screen.queryByTestId('vworld-map')).toBeNull();
    expect(screen.getByText('경포대')).toBeTruthy();
  });
});
