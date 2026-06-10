import { describe, expect, it } from 'vitest';
import type { TripViewDay, TripViewPoi } from '@tripmate/schemas';
import {
  extractCoord,
  pointsBounds,
  tripDaysToMapPoints,
  tripPoiToMapPoint,
} from '@/lib/tripMapPoints';

function poi(over: Partial<TripViewPoi> & { feature: Record<string, unknown> }): TripViewPoi {
  return {
    poi_id: '11111111-1111-1111-1111-111111111111',
    feature_id: 'feat-1',
    sort_order: 'n',
    title: '경복궁',
    marker_color: 'P-09',
    marker_icon: 'museum',
    is_broken: false,
    user_note: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    rise_set: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-06-10T00:00:00Z',
    updated_at: '2026-06-10T00:00:00Z',
    ...over,
  } as TripViewPoi;
}

describe('tripMapPoints', () => {
  it('extractCoord: feature.coord 추출, 한국 범위 밖/누락은 null', () => {
    expect(extractCoord({ coord: { lon: 126.97, lat: 37.57 } })).toEqual({ lon: 126.97, lat: 37.57 });
    expect(extractCoord({ coord: { lon: 0, lat: 0 } })).toBeNull(); // 범위 밖
    expect(extractCoord({})).toBeNull();
    expect(extractCoord(null)).toBeNull();
    expect(extractCoord('nope')).toBeNull();
  });

  it('tripPoiToMapPoint: 좌표 있으면 포인트, marker_color → hex', () => {
    const point = tripPoiToMapPoint(poi({ feature: { coord: { lon: 126.977, lat: 37.5796 } } }), 1);
    expect(point).toMatchObject({
      poiId: '11111111-1111-1111-1111-111111111111',
      dayIndex: 1,
      title: '경복궁',
      lon: 126.977,
      lat: 37.5796,
      color: '#3949AB',
      icon: 'museum',
      isBroken: false,
    });
  });

  it('tripPoiToMapPoint: 좌표 없으면 null (broken/snapshot 누락)', () => {
    expect(tripPoiToMapPoint(poi({ feature: {} }), 1)).toBeNull();
  });

  it('tripPoiToMapPoint: title 없으면 feature_id fallback', () => {
    const point = tripPoiToMapPoint(
      poi({ title: null, feature_id: 'feat-x', feature: { coord: { lon: 127, lat: 37 } } }),
      2
    );
    expect(point?.title).toBe('feat-x');
  });

  it('tripDaysToMapPoints: 여러 day 의 POI 평탄화 (좌표 없는 것 제외)', () => {
    const days: TripViewDay[] = [
      {
        day_index: 1,
        date: null,
        title: '1일차',
        pois: [
          poi({ feature: { coord: { lon: 126.9, lat: 37.5 } } }),
          poi({ feature: {} }), // 제외
        ],
      },
      {
        day_index: 2,
        date: null,
        title: '2일차',
        pois: [poi({ feature: { coord: { lon: 129.0, lat: 35.1 } } })],
      },
    ];
    const points = tripDaysToMapPoints(days);
    expect(points).toHaveLength(2);
    expect(points.map((p) => p.dayIndex)).toEqual([1, 2]);
  });

  it('pointsBounds: 모든 POI 를 담는 경계, 비면 null', () => {
    expect(pointsBounds([])).toBeNull();
    const days: TripViewDay[] = [
      {
        day_index: 1,
        date: null,
        title: null,
        pois: [
          poi({ feature: { coord: { lon: 126.9, lat: 37.5 } } }),
          poi({ feature: { coord: { lon: 129.0, lat: 35.1 } } }),
        ],
      },
    ];
    expect(pointsBounds(tripDaysToMapPoints(days))).toEqual({
      west: 126.9,
      south: 35.1,
      east: 129.0,
      north: 37.5,
    });
  });
});
