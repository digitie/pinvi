import { describe, expect, it } from 'vitest';
import { ApiClient, featureApi } from '@pinvi/api-client';
import {
  FeatureGeometrySchema,
  FeatureSummarySchema,
  FeaturesInBoundsResponseSchema,
} from '@pinvi/schemas';

const outer = [
  [127, 37.5],
  [127.02, 37.5],
  [127.02, 37.52],
  [127, 37.5],
];
const hole = [
  [127.005, 37.505],
  [127.01, 37.505],
  [127.01, 37.51],
  [127.005, 37.505],
];
const geometries = [
  { type: 'LineString', coordinates: outer.slice(0, 2) },
  { type: 'MultiLineString', coordinates: [outer.slice(0, 2), hole.slice(0, 2)] },
  { type: 'Polygon', coordinates: [outer, hole] },
  { type: 'MultiPolygon', coordinates: [[outer, hole], [outer]] },
];
const emptyBounds = {
  items: [],
  clusters: [],
  zoom: 14,
  bbox: { lng_min: 127, lat_min: 37.5, lng_max: 127.1, lat_max: 37.6 },
};

describe('#635 geometry wire contract', () => {
  it.each(geometries)('보조 point 없이 원래 도형을 보존한다: $type', (geometry) => {
    const parsed = FeatureSummarySchema.parse({
      feature_id: 'geometry:635',
      kind: geometry.type.includes('LineString') ? 'route' : 'area',
      name: '도형 검증',
      coord: null,
      marker_color: 'P-06',
      marker_icon: 'walking',
      geometry,
    });
    expect(parsed).toHaveProperty('geometry', geometry);
    expect(parsed.coord).toBeNull();
  });

  it('잘린 결과를 완결로 바꾸지 않는다', () => {
    const data = FeaturesInBoundsResponseSchema.parse({ ...emptyBounds, truncated: true });
    expect(data).toHaveProperty('truncated', true);
  });

  it('API 요청에 geometry 선택을 명시하고 결과도 보존한다', async () => {
    let seen = '';
    const fetcher = ((url: string) => {
      seen = url;
      return Promise.resolve(
        new Response(JSON.stringify({ data: { ...emptyBounds, truncated: true } })),
      );
    }) as typeof fetch;
    const client = new ApiClient({ baseUrl: 'http://fixture.test', fetcher });
    const result = await featureApi(client).inBounds({
      bbox: '127,37.5,127.1,37.6',
      zoom: 14,
      kinds: ['route', 'area'],
      includeGeometry: true,
    });
    expect(new URL(seen).searchParams.get('include_geometry')).toBe('true');
    expect(result).toHaveProperty('truncated', true);
  });
});

it.each([
  { type: 'Polygon', coordinates: [[]] },
  {
    type: 'Polygon',
    coordinates: [
      [
        [127, 37.5],
        [127.1, 37.5],
        [127.1, 37.6],
        [127, 37.6],
      ],
    ],
  },
  {
    type: 'LineString',
    coordinates: [
      [127, NaN],
      [127.1, 37.6],
    ],
  },
  {
    type: 'LineString',
    coordinates: [
      [181, 37.5],
      [127.1, 37.6],
    ],
  },
])('잘못된 도형을 예외 누출 없이 거부한다: %j', (geometry) => {
  expect(FeatureGeometrySchema.safeParse(geometry).success).toBe(false);
});

it('도형 하나가 잘못돼도 응답 전체를 거부하지 않고 그 도형만 비운다', () => {
  const item = (feature_id: string, geometry: unknown) => ({
    feature_id,
    kind: 'route',
    name: feature_id,
    coord: null,
    marker_color: 'P-01',
    marker_icon: 'route',
    geometry,
  });
  const parsed = FeaturesInBoundsResponseSchema.parse({
    ...emptyBounds,
    items: [
      item('route:good', geometries[0]),
      item('route:bad', { type: 'LineString', coordinates: [[127, 37.5]] }),
    ],
  });
  expect(parsed.items.map((x) => x.feature_id)).toEqual(['route:good', 'route:bad']);
  expect(parsed.items[0]!.geometry).toEqual(geometries[0]);
  expect(parsed.items[1]!.geometry).toBeNull();
});
