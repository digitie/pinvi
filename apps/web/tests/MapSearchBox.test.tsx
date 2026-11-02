import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { PlaceSearchResult } from '@pinvi/schemas';

// 통합 검색은 geoApi(apiClient).searchPlaces로 나간다 — 그 한 지점만 스텁한다.
const searchPlaces = vi.fn();
vi.mock('@/lib/api', () => ({ apiClient: {} }));
vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  return { ...actual, geoApi: () => ({ searchPlaces }) };
});

import { MapSearchBox } from '@/components/map/MapSearchBox';

function makeResult(over: Partial<PlaceSearchResult>): PlaceSearchResult {
  return {
    source: 'feature',
    name: '테스트',
    coord: { lon: 129.1, lat: 35.1 },
    feature_id: null,
    poi_id: null,
    trip_id: null,
    trip_title: null,
    external_id: null,
    address: null,
    road_address: null,
    category: null,
    category_label: null,
    marker_color: null,
    marker_icon: null,
    provider_url: null,
    phone: null,
    ...over,
  };
}

beforeEach(() => {
  searchPlaces.mockReset();
});

describe('MapSearchBox', () => {
  it('feature 결과의 둘째 줄은 카테고리 코드가 아니라 이름이다(2026-11-02 prod e2e)', async () => {
    searchPlaces.mockResolvedValue({
      results: [
        makeResult({
          source: 'feature',
          name: '하회마을',
          feature_id: 'f-restaurant',
          category: '02010100',
          category_label: '한식',
        }),
        makeResult({
          source: 'feature',
          name: '도산서원',
          feature_id: 'f-unknown',
          category: '99010100',
          category_label: null,
        }),
        makeResult({
          source: 'kakao',
          name: '하회마을 카페',
          external_id: 'k1',
          category: '음식점 > 카페',
        }),
      ],
      degraded_sources: [],
    });
    render(<MapSearchBox onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('장소·주소 검색'), { target: { value: '하회마을' } });

    const rows = await screen.findAllByTestId('map-search-result-feature');
    expect(rows[0]).toHaveTextContent('한식');
    expect(rows[0]).not.toHaveTextContent('02010100');
    // 이름을 모르는 코드는 숫자로 보이지 않고 비운다.
    expect(rows[1]).not.toHaveTextContent('99010100');
    // 외부 provider의 category는 이미 사람이 읽는 이름이다.
    expect(screen.getByTestId('map-search-result-kakao')).toHaveTextContent('음식점 > 카페');
  });

  it('2자 이상 입력 시 디바운스 후 검색하고 source별 배지/주소로 렌더한다', async () => {
    searchPlaces.mockResolvedValue({
      results: [
        makeResult({
          source: 'feature',
          name: '광안리',
          feature_id: 'f1',
          road_address: '부산 수영구',
        }),
        makeResult({
          source: 'kakao',
          name: '광안리 카페',
          external_id: 'k1',
          address: '부산 수영구 광안동',
          provider_url: 'https://place.map.kakao.com/k1',
        }),
        makeResult({ source: 'naver', name: '광안리 횟집', external_id: 'n1' }),
      ],
      degraded_sources: [],
    });
    render(<MapSearchBox onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('장소·주소 검색'), { target: { value: '광안리' } });

    expect(await screen.findByTestId('map-search-result-feature')).toHaveTextContent('광안리');
    // kakao/naver는 약관상 가시적 attribution이 필요(ADR-054 M19).
    expect(screen.getByText('카카오')).toBeInTheDocument();
    expect(screen.getByText('네이버 검색')).toBeInTheDocument();
    expect(screen.getByText('부산 수영구')).toBeInTheDocument();
    // §5.2(HARD): provider_url이 있는 kakao/naver 행은 back-link를 표시한다.
    const backLink = screen.getByTestId('map-search-backlink-kakao');
    expect(backLink).toHaveAttribute('href', 'https://place.map.kakao.com/k1');
    expect(backLink).toHaveAttribute('target', '_blank');
    expect(backLink).toHaveAttribute('rel', 'noopener noreferrer');
    expect(searchPlaces).toHaveBeenCalledWith(
      { q: '광안리', limit: 8 },
      expect.objectContaining({ signal: expect.anything() }),
    );
  });

  it('결과 클릭 시 onSelect에 PlaceSearchResult 전체를 넘기고 목록을 닫는다', async () => {
    const picked = makeResult({
      source: 'kakao',
      name: '카페',
      external_id: 'k1',
      provider_url: 'https://map.kakao.com/x',
    });
    searchPlaces.mockResolvedValue({ results: [picked], degraded_sources: [] });
    const onSelect = vi.fn();
    render(<MapSearchBox onSelect={onSelect} />);
    fireEvent.change(screen.getByLabelText('장소·주소 검색'), { target: { value: '카페' } });

    fireEvent.click(await screen.findByTestId('map-search-result-kakao'));
    expect(onSelect).toHaveBeenCalledWith(picked);
    expect(screen.queryByTestId('map-search-result-kakao')).not.toBeInTheDocument();
  });

  it('2자 미만이면 검색하지 않는다', async () => {
    render(<MapSearchBox onSelect={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('장소·주소 검색'), { target: { value: 'a' } });
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(searchPlaces).not.toHaveBeenCalled();
  });
});
