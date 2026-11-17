import { describe, expect, it } from 'vitest';
import { CATEGORY_MARKER, paletteHex } from '@pinvi/domain';
import type { FeaturesInBoundsResponse, PlaceSearchResult } from '@pinvi/schemas';
import { CLUSTER_COLOR, explorePointFromSearch, toExplorePoints } from '@/lib/exploreMapPoints';

/**
 * 탐색 지도 장소 마커의 원 색·아이콘(소유자 요청 2026-11-17 "탐색지도의 마커도 여행과 동일하게").
 * 탐색 지도의 장소에는 사용자가 고른 색·아이콘이 없다 — 여행 지도 feature 마커와 같은 규칙
 * (`resolveMarkerStyle`: Map이 준 값 → 카테고리 → kind → 회색)으로 정한다.
 */
const BBOX = { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 };

function response(items: FeaturesInBoundsResponse['items']): FeaturesInBoundsResponse {
  return { items, clusters: [], zoom: 14, bbox: BBOX };
}

describe('toExplorePoints — 원 색·아이콘', () => {
  it('Map이 준 marker_color/marker_icon을 그대로 쓴다', () => {
    const [point] = toExplorePoints(
      response([
        {
          feature_id: 'f-1',
          kind: 'place',
          name: '경복궁',
          coord: { lon: 126.977, lat: 37.579 },
          category: '국가유산',
          marker_color: 'P-09',
          marker_icon: 'museum',
        },
      ]),
    );
    expect(point).toMatchObject({
      kind: 'feature',
      featureId: 'f-1',
      title: '경복궁',
      icon: 'museum',
      markerColor: 'P-09',
      color: paletteHex('P-09'),
      markerSource: 'upstream',
      lngLat: [126.977, 37.579],
    });
  });

  it('Map 아이콘이 비면 카테고리 매핑(CATEGORY_MARKER)으로 아이콘을 정한다', () => {
    const [point] = toExplorePoints(
      response([
        {
          feature_id: 'f-2',
          kind: 'place',
          name: '어느 카페',
          coord: { lon: 127, lat: 37.5 },
          category: '카페',
          marker_color: 'P-12',
          marker_icon: '',
        },
      ]),
    );
    expect(point?.icon).toBe(CATEGORY_MARKER['카페']!.icon);
    expect(point?.category).toBe('카페');
  });

  it('좌표 없는 feature는 마커에서 빼고, 서버 묶음은 회색 묶음 point가 된다', () => {
    const points = toExplorePoints({
      items: [
        {
          feature_id: 'f-3',
          kind: 'area',
          name: '좌표 없음',
          coord: null,
          marker_color: 'P-05',
          marker_icon: 'park',
        },
      ],
      clusters: [{ cluster_key: '11110', coord: { lon: 126.98, lat: 37.57 }, feature_count: 31 }],
      zoom: 12,
      bbox: BBOX,
    });
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      kind: 'cluster',
      color: CLUSTER_COLOR,
      title: '31곳',
      count: 31,
    });
    expect(points[0]?.featureId).toBeUndefined();
  });
});

describe('explorePointFromSearch', () => {
  const base: PlaceSearchResult = {
    source: 'feature',
    name: '서울역',
    coord: { lon: 126.9707, lat: 37.5547 },
    feature_id: 'f-seoul',
    poi_id: null,
    trip_id: null,
    trip_title: null,
    external_id: null,
    address: null,
    road_address: null,
    category: '관광명소',
    category_label: '관광명소',
    marker_color: null,
    marker_icon: null,
    provider_url: null,
    phone: null,
  };

  it('feature 결과는 카테고리 색·아이콘으로 선택 point가 된다', () => {
    expect(explorePointFromSearch(base)).toMatchObject({
      kind: 'feature',
      featureId: 'f-seoul',
      icon: CATEGORY_MARKER['관광명소']!.icon,
      markerColor: CATEGORY_MARKER['관광명소']!.color,
      markerSource: 'category',
    });
  });

  it('feature가 아니거나 좌표가 없으면 null', () => {
    expect(explorePointFromSearch({ ...base, feature_id: null, source: 'kakao' })).toBeNull();
    expect(explorePointFromSearch({ ...base, coord: null })).toBeNull();
  });
});
