import type { FeatureGeometry, FeatureSummary } from '@pinvi/schemas';

export type GeometryKind = 'route' | 'area';
export type GeometryFeature = FeatureSummary & { kind: GeometryKind; geometry: FeatureGeometry };
export const MIN_GEOMETRY_ZOOM = 14;

export function geometryZoomEligible(rawZoom: number): boolean {
  return Number.isFinite(rawZoom) && rawZoom >= MIN_GEOMETRY_ZOOM;
}

export function isGeometryFeature(feature: FeatureSummary): feature is GeometryFeature {
  const type = feature.geometry?.type;
  return (
    (feature.kind === 'route' && (type === 'LineString' || type === 'MultiLineString')) ||
    (feature.kind === 'area' && (type === 'Polygon' || type === 'MultiPolygon'))
  );
}

/** 모든 part와 내부 ring을 순회하되 원래 geometry를 바꾸지 않는다. */
export function geometryBounds(
  geometry: FeatureGeometry,
): [[number, number], [number, number]] | null {
  let west = Infinity,
    south = Infinity,
    east = -Infinity,
    north = -Infinity;
  const visit = (value: unknown): void => {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === 'number' && typeof value[1] === 'number') {
      west = Math.min(west, value[0]);
      east = Math.max(east, value[0]);
      south = Math.min(south, value[1]);
      north = Math.max(north, value[1]);
      return;
    }
    value.forEach(visit);
  };
  visit(geometry.coordinates);
  if (![west, south, east, north].every(Number.isFinite)) return null;
  return [
    [west, south],
    [east, north],
  ];
}

export function geometryQueryKey(
  bbox: string,
  zoom: number,
  kinds: readonly GeometryKind[],
  category?: string,
): string {
  return JSON.stringify({
    bbox,
    zoom,
    kinds: [...kinds].sort(),
    category: category || null,
    includeGeometry: true,
  });
}
