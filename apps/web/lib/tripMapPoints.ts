/**
 * TripView(POI) → 지도 포인트 변환 — PR-C(2).
 *
 * `TripViewPoi.feature` 는 opaque dict(krtour fresh 또는 snapshot)라 좌표를 런타임 검증으로
 * 꺼낸다(`CoordSchema`). 좌표가 없거나 한국 범위 밖이면 지도에 올리지 않는다(null).
 */

import { CoordSchema } from '@tripmate/schemas';
import type { TripViewDay, TripViewPoi } from '@tripmate/schemas';
import { paletteHex } from './markerPalette';

export interface TripMapPoint {
  poiId: string;
  dayIndex: number;
  title: string;
  lon: number;
  lat: number;
  /** 렌더용 hex (marker_color → 팔레트, 없으면 회색). */
  color: string;
  markerColor: string | null;
  icon: string;
  isBroken: boolean;
}

/** opaque feature dict 에서 `coord.{lon,lat}` 를 안전하게 추출. 실패 시 null. */
export function extractCoord(feature: unknown): { lon: number; lat: number } | null {
  if (!feature || typeof feature !== 'object') {
    return null;
  }
  const coord = (feature as Record<string, unknown>).coord;
  const parsed = CoordSchema.safeParse(coord);
  return parsed.success ? parsed.data : null;
}

export function tripPoiToMapPoint(poi: TripViewPoi, dayIndex: number): TripMapPoint | null {
  const coord = extractCoord(poi.feature);
  if (!coord) {
    return null;
  }
  return {
    poiId: poi.poi_id,
    dayIndex,
    title: poi.title ?? poi.feature_id ?? '장소',
    lon: coord.lon,
    lat: coord.lat,
    color: paletteHex(poi.marker_color),
    markerColor: poi.marker_color,
    icon: poi.marker_icon ?? 'marker',
    isBroken: poi.is_broken,
  };
}

export function tripDaysToMapPoints(days: TripViewDay[]): TripMapPoint[] {
  const points: TripMapPoint[] = [];
  for (const day of days) {
    for (const poi of day.pois) {
      const point = tripPoiToMapPoint(poi, day.day_index);
      if (point) {
        points.push(point);
      }
    }
  }
  return points;
}

export interface PointBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

/** POI 들을 모두 담는 경계. 비어 있으면 null. */
export function pointsBounds(points: TripMapPoint[]): PointBounds | null {
  const first = points[0];
  if (!first) {
    return null;
  }
  let west = first.lon;
  let east = first.lon;
  let south = first.lat;
  let north = first.lat;
  for (const p of points) {
    west = Math.min(west, p.lon);
    east = Math.max(east, p.lon);
    south = Math.min(south, p.lat);
    north = Math.max(north, p.lat);
  }
  return { west, south, east, north };
}
