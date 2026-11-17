import type { ClusterPoint } from '@/components/map/vworldPrimitives';
import type { FeaturesInBoundsResponse, PlaceSearchResult } from '@pinvi/schemas';
import { resolveMarkerStyle } from '@pinvi/domain';

/**
 * 탐색 지도(`/map`) 마커 point. 장소 마커는 여행 지도와 같은 원형 마커(`CirclePlaceMarker`)로 그린다.
 *
 * 탐색 지도의 장소에는 사용자가 고른 색·아이콘이 없다 — 원 색과 원 안 아이콘은 여행 지도의 feature 마커와
 * 같은 규칙(`resolveMarkerStyle`: Map이 준 marker_color/marker_icon → 카테고리(`CATEGORY_MARKER`) →
 * kind(`KIND_MARKER`) → 회색 기본)으로 정한다.
 */
export type ExploreMapPoint = ClusterPoint & {
  kind: 'feature' | 'cluster';
  /** 원 채움색(hex). */
  color: string;
  /** 팔레트 키(P-01…) 또는 묶음 표식. */
  markerColor: string;
  markerSource: string;
  /** maki 아이콘 이름. */
  icon: string;
  title: string;
  lon: number;
  lat: number;
  category?: string | null;
  featureId?: string;
  count?: number;
};

export const CLUSTER_COLOR = '#37404a';
const CLUSTER_MARKER_COLOR = 'cluster';

/** in-bounds 응답 → 지도 point. point geometry(평면 lon/lat)가 없는 feature는 마커에서 뺀다. */
export function toExplorePoints(data: FeaturesInBoundsResponse): ExploreMapPoint[] {
  const features: ExploreMapPoint[] = data.items.flatMap((f) => {
    if (!f.coord) return [];
    const style = resolveMarkerStyle({
      upstreamColor: f.marker_color,
      upstreamIcon: f.marker_icon,
      upstreamCategory: f.category,
      upstreamKind: f.kind,
    });
    return [
      {
        id: f.feature_id,
        lngLat: [f.coord.lon, f.coord.lat] as [number, number],
        kind: 'feature' as const,
        color: style.hex,
        markerColor: style.color,
        markerSource: style.source,
        icon: style.icon,
        title: f.name,
        lon: f.coord.lon,
        lat: f.coord.lat,
        category: style.category,
        featureId: f.feature_id,
      },
    ];
  });
  const clusters: ExploreMapPoint[] = data.clusters.map((c) => ({
    id: c.cluster_key,
    lngLat: [c.coord.lon, c.coord.lat],
    kind: 'cluster',
    color: CLUSTER_COLOR,
    markerColor: CLUSTER_MARKER_COLOR,
    markerSource: 'cluster',
    icon: 'circle',
    title: `${c.feature_count}곳`,
    lon: c.coord.lon,
    lat: c.coord.lat,
    count: c.feature_count,
  }));
  return [...features, ...clusters];
}

/** 검색 결과(feature)로 고른 장소 → 선택 point. feature가 아니거나 좌표가 없으면 null. */
export function explorePointFromSearch(result: PlaceSearchResult): ExploreMapPoint | null {
  const coord = result.coord;
  if (!coord || result.feature_id == null) return null;
  const style = resolveMarkerStyle({
    upstreamColor: result.marker_color,
    upstreamIcon: result.marker_icon,
    upstreamCategory: result.category,
  });
  return {
    id: result.feature_id,
    lngLat: [coord.lon, coord.lat],
    kind: 'feature',
    color: style.hex,
    markerColor: style.color,
    markerSource: style.source,
    icon: style.icon,
    title: result.name,
    lon: coord.lon,
    lat: coord.lat,
    category: style.category,
    featureId: result.feature_id,
  };
}
