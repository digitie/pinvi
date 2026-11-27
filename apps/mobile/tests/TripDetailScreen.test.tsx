import { useImperativeHandle } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlatformMarkerItem, PlatformVWorldMapProps } from '../components/VWorldMap.types';
import { rainyDayCard, rainyPoiCard } from './fixtures/weather';

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

const auth = vi.hoisted(() => ({ userId: 'user-owner' as string | null }));
vi.mock('../lib/auth', () => ({
  useAuth: () => ({ user: auth.userId ? { user_id: auth.userId } : null }),
}));

vi.mock('expo-router', () => ({
  useLocalSearchParams: () => ({ tripId: 'trip-1' }),
  useRouter: () => ({ push: vi.fn() }),
}));

const emptyWeather = (path: string): unknown => ({
  feature_id: path,
  is_stale: false,
  source_styles: [],
  metrics: [],
});

const server = vi.hoisted(() => ({
  paths: [] as string[],
  transportEnabled: true,
  // 장소별 현재 날씨 — 기본은 빈 카드(날씨 모름).
  weather: null as null | ((path: string) => unknown),
  // 저장된 영업 정보 — 경포대만 전화가 있다.
  placeDetails: (path: string): unknown => ({
    opening_hours: ['매일 09:00~18:00'],
    closed_days: null,
    phone: path.includes('poi-a') ? '033-640-5000' : null,
    website: null,
    sources: { opening_hours: 'kor_travel_map' },
    fetched_at: '2026-11-17T00:00:00Z',
  }),
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
    weather_cards: {},
    weather_by_feature_id: {},
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
    owner_user_id: 'user-owner',
  },
  companions: [{ user_id: 'user-viewer', role: 'viewer' }],
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
      if (path.endsWith('/place-details/kakao-phone')) {
        return {
          provider: 'kakao',
          matched: true,
          name: null,
          address: null,
          phone: '033-111-2222',
          provider_url: 'https://place.map.kakao.com/1',
          external_id: '1',
        };
      }
      if (path.endsWith('/place-details')) {
        return server.placeDetails(path);
      }
      if (/^\/features\/[^/]+\/detail-card$/.test(path)) {
        return detailCard(path);
      }
      if (/^\/trips\/trip-1\/pois\/[^/]+\/weather$/.test(path)) {
        return (server.weather ?? emptyWeather)(path);
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

// 경포대(poi-a)만 TourAPI 소개(대표 이미지·소개문)가 있다. 나머지는 소개 없는 place 카드다.
function detailCard(path: string) {
  const withIntro = path.includes('feature-poi-a');
  return {
    kind: 'place',
    feature_id: path.split('/')[2],
    name: '경포대',
    marker_color: 'P-02',
    marker_icon: 'attraction',
    introduction: withIntro
      ? {
          provider: 'tourapi',
          attribution: '한국관광공사',
          overview: '경포대는 강릉시 저동에 있는 누각이다.',
          images: [
            {
              url: 'https://tong.visitkorea.or.kr/cms/resource/b.jpg',
              alt: '경포대 대표 사진',
              kogl_type: 3,
              no_derivatives: true,
            },
          ],
          kogl_type: 3,
          license_label: '공공누리 제3유형: 출처표시 + 변경금지',
          license_url: 'https://www.kogl.or.kr/info/licenseType3.do',
        }
      : null,
  };
}

// 경포대(poi-a)는 여행 응답의 일자 날씨 카드로 비가 온다(마커 날씨는 새 요청 없이 이 카드에서).
Object.assign(TRIP_VIEW.days[0]!, {
  weather_cards: { 'card-1': rainyDayCard() },
  weather_by_feature_id: { 'feature-poi-a': { state: 'found', card_key: 'card-1' } },
});

const { default: TripDetailScreen } = await import('../app/(app)/trips/[tripId]/index');
const { poiWeatherStore } = await import('../lib/poiWeather');

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
  server.weather = null;
  auth.userId = 'user-owner';
  poiWeatherStore.reset();
});

describe('모바일 여행 상세 지도', () => {
  it('마커는 원 안 아이콘과 이름 옆 현재 날씨를 싣고, 목록 줄은 좌표를 아는 장소만 날씨를 묻는다', async () => {
    server.weather = (path) => (path.includes('poi-b') ? rainyPoiCard() : emptyWeather(path));
    renderScreen();
    await screen.findByTestId('vworld-map');
    const poiA = () => markers().find((m) => m.id === 'poi:poi-a');
    const poiB = () => markers().find((m) => m.id === 'poi:poi-b');
    // 아이콘 없는 장소도 기본 핀 아이콘(웹과 같은 해석).
    expect(poiA()?.icon).toBeTruthy();
    // 일자 카드에서 — 요청 없이.
    await waitFor(() => expect(poiA()?.weather).toMatchObject({ condition: 'rain' }));
    // 장소별 현재 카드(목록 배지가 받은 공유 캐시)에서.
    await waitFor(() => expect(poiB()?.weather).toMatchObject({ condition: 'rain' }));
    expect(markers().find((m) => m.id === 'poi:poi-c')?.weather).toBeNull();

    const badge = await within(screen.getByTestId('trip-poi-row-poi-b')).findByTestId(
      'weather-badge',
    );
    expect(badge.textContent).toContain('12');
    const weatherRequests = server.paths.filter((p) => p.endsWith('/weather'));
    expect(weatherRequests.some((p) => p.includes('poi-d'))).toBe(false);
    expect(weatherRequests.filter((p) => p.includes('poi-b'))).toHaveLength(1);
  });

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

  it('지도 마커를 누르면 읽기 전용 장소 시트가 열리고, 요약만 보이며 항목은 접혀 있다', async () => {
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'marker 경포대' }));
    const sheet = await screen.findByTestId('place-sheet');
    expect(within(sheet).getByTestId('place-sheet-title').textContent).toBe('경포대');
    expect(within(sheet).queryByTestId('place-sheet-hours')).toBeNull();
    expect(within(sheet).queryByTestId('place-sheet-memo')).toBeNull();
    // 저장된 영업시간 요약(오늘 줄)은 요약에 늘 보인다.
    expect(await within(sheet).findByTestId('place-sheet-today-hours')).toBeTruthy();
    // 편집할 수 있는 사람(소유자)에게만 편집 화면 연결.
    expect(within(sheet).getByRole('button', { name: '장소 편집' })).toBeTruthy();
  });

  it('영업 정보: 저장된 전화가 있으면 카카오를 부르지 않고, 없으면 카카오 전화를 출처와 함께 보인다', async () => {
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'marker 경포대' }));
    let sheet = await screen.findByTestId('place-sheet');
    fireEvent.click(within(sheet).getByTestId('place-sheet-hours-toggle'));
    expect((await within(sheet).findByTestId('place-sheet-phone')).textContent).toBe(
      '033-640-5000',
    );
    expect(server.paths.some((p) => p.endsWith('/kakao-phone'))).toBe(false);
    fireEvent.click(within(sheet).getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByTestId('place-sheet')).toBeNull());

    // 목록 줄의 '정보' 버튼으로도 연다.
    fireEvent.click(screen.getByRole('button', { name: '안목해변 장소 정보' }));
    sheet = await screen.findByTestId('place-sheet');
    fireEvent.click(within(sheet).getByTestId('place-sheet-hours-toggle'));
    const kakao = await within(sheet).findByTestId('place-sheet-kakao-phone');
    expect(kakao.textContent).toContain('033-111-2222');
    expect(kakao.textContent).toContain('출처: 카카오맵');
    expect(server.paths.filter((p) => p.endsWith('/kakao-phone'))).toHaveLength(1);
  });

  it('TourAPI 소개가 있는 장소는 소개 항목이 맨 앞에 생기고 원본 비율 이미지·출처를 보인다', async () => {
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'marker 경포대' }));
    const sheet = await screen.findByTestId('place-sheet');
    const toggle = await within(sheet).findByTestId('place-sheet-about-toggle');
    expect(toggle.textContent).toBe('소개');
    fireEvent.click(toggle);
    const intro = await within(sheet).findByTestId('place-sheet-introduction');
    expect(within(intro).getByTestId('place-sheet-introduction-overview').textContent).toContain(
      '누각',
    );
    expect(within(intro).getByTestId('place-sheet-introduction-attribution').textContent).toContain(
      '출처: 한국관광공사',
    );
    expect(within(intro).getByTestId('place-sheet-introduction-license').textContent).toContain(
      '제3유형',
    );
    expect(
      within(intro).getByRole('link', { name: '경포대 대표 사진 — 원본 이미지 열기' }),
    ).toBeTruthy();
  });

  it('소개가 없는 장소는 소개 항목을 만들지 않는다', async () => {
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'marker 오죽헌' }));
    const sheet = await screen.findByTestId('place-sheet');
    await waitFor(() =>
      expect(server.paths.some((p) => p.endsWith('/detail-card') && p.includes('poi-'))).toBe(true),
    );
    expect(within(sheet).queryByTestId('place-sheet-about-toggle')).toBeNull();
  });

  it('메모·지도 앱 항목, 보기 전용 동행에게는 편집 연결이 없다', async () => {
    auth.userId = 'user-viewer';
    renderScreen();
    fireEvent.click(await screen.findByRole('button', { name: 'marker 오죽헌' }));
    const sheet = await screen.findByTestId('place-sheet');
    expect(within(sheet).queryByRole('button', { name: '장소 편집' })).toBeNull();
    fireEvent.click(within(sheet).getByTestId('place-sheet-memo-toggle'));
    expect(within(sheet).getByTestId('place-sheet-memo').textContent).toContain('메모가 없습니다');
    fireEvent.click(within(sheet).getByTestId('place-sheet-maps-toggle'));
    expect(within(sheet).getByTestId('place-sheet-map-naver')).toBeTruthy();
    expect(within(sheet).getByTestId('place-sheet-map-kakao')).toBeTruthy();
    expect(within(sheet).getByTestId('place-sheet-map-google')).toBeTruthy();
    // 메모를 펼치면 다른 항목은 접힌다(한 번에 하나).
    expect(within(sheet).queryByTestId('place-sheet-memo')).toBeNull();
  });
});
