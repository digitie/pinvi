import { describe, expect, it } from 'vitest';
import type { FeatureGeometry } from '@pinvi/schemas';
import {
  geometryBounds,
  geometryQueryKey,
  geometryZoomEligible,
  isGeometryFeature,
} from '@/lib/featureGeometry';
import type { GeometryFeature } from '@/lib/featureGeometry';

describe('geometry viewport and bounds', () => {
  it.each([13, 13.49, 13.5, 13.999, NaN, Infinity])('반올림 전 확대 하한을 지킨다: %s', (zoom) => {
    expect(geometryZoomEligible(zoom)).toBe(false);
  });
  it.each([14, 14.001, 16])('확대 하한 이상을 허용한다: %s', (zoom) => {
    expect(geometryZoomEligible(zoom)).toBe(true);
  });
  it.each([
    {
      type: 'LineString',
      coordinates: [
        [126, 35],
        [129, 38],
      ],
    },
    {
      type: 'MultiLineString',
      coordinates: [
        [
          [127, 36],
          [128, 37],
        ],
        [
          [126, 35],
          [129, 38],
        ],
      ],
    },
    {
      type: 'Polygon',
      coordinates: [
        [
          [126, 35],
          [129, 35],
          [129, 38],
          [126, 35],
        ],
        [
          [127, 36],
          [128, 36],
          [128, 37],
          [127, 36],
        ],
      ],
    },
    {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [127, 36],
            [128, 36],
            [128, 37],
            [127, 36],
          ],
        ],
        [
          [
            [126, 35],
            [129, 35],
            [129, 38],
            [126, 35],
          ],
        ],
      ],
    },
  ])('모든 part와 ring을 보존한 전체 bounds: $type', (geometry) => {
    const before = structuredClone(geometry);
    expect(geometryBounds(geometry as FeatureGeometry)).toEqual([
      [126, 35],
      [129, 38],
    ]);
    expect(geometry).toEqual(before);
  });
  it.each([
    { coordinates: [] },
    {
      coordinates: [
        [NaN, 35],
        [129, 38],
      ],
    },
  ])('유효 좌표가 없는 bounds는 사용하지 않는다', ({ coordinates }) => {
    expect(geometryBounds({ type: 'LineString', coordinates } as FeatureGeometry)).toBeNull();
  });
  it('kind/category/bbox/zoom은 cache scope이며 kind 순서만 무관하다', () => {
    const a = geometryQueryKey('a', 14, ['route', 'area'], 'cat');
    expect(a).toBe(geometryQueryKey('a', 14, ['area', 'route'], 'cat'));
    for (const other of [
      geometryQueryKey('b', 14, ['route', 'area'], 'cat'),
      geometryQueryKey('a', 15, ['route', 'area'], 'cat'),
      geometryQueryKey('a', 14, ['route'], 'cat'),
      geometryQueryKey('a', 14, ['route', 'area'], 'other'),
    ])
      expect(other).not.toBe(a);
  });
  it('kind와 geometry가 맞지 않으면 지도 도형으로 취급하지 않는다', () => {
    const feature = {
      kind: 'route',
      geometry: { type: 'Polygon', coordinates: [] },
    } as unknown as GeometryFeature;
    expect(isGeometryFeature(feature)).toBe(false);
    expect(isGeometryFeature({ ...feature, geometry: null })).toBe(false);
  });
});
