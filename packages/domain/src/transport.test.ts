import { describe, expect, it } from 'vitest';
import type { HighwayIncidentItem, TransportLayer, TransportLayerResult } from '@pinvi/schemas';
import {
  dedupeTransportNearPoints,
  formatFuelPrice,
  fuelProductLabel,
  parseTransportMarkerId,
  requestableTransportLayers,
  sortIncidentsByRecency,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportMarkerId,
  transportLayerStatusText,
  transportNearPointsKey,
  transportRadiusLabel,
  TRANSPORT_LAYER_META,
  TRANSPORT_STATUS_LOADING_TEXT,
  withUnavailableTransportLayers,
  type TransportLayerStatusInput,
} from './transport';

describe('requestableTransportLayers', () => {
  const all = new Set<TransportLayer>(['fuel_station', 'rest_area', 'highway_incident', 'airport']);

  it('줌이 낮으면 최소 줌 이상인 레이어만 요청한다', () => {
    expect(requestableTransportLayers(all, 6)).toEqual([]);
    expect(requestableTransportLayers(all, 8)).toEqual(['highway_incident']);
    expect(requestableTransportLayers(all, 11)).toEqual(['fuel_station', 'highway_incident']);
  });

  it('휴게소·공항은 지도에서 뺐다 — 켜져 있어도 요청하지 않는다', () => {
    expect(TRANSPORT_LAYER_META.map((meta) => meta.layer)).toEqual([
      'fuel_station',
      'highway_incident',
    ]);
    expect(requestableTransportLayers(new Set(['rest_area', 'airport']), 15)).toEqual([]);
  });

  it('반경 문구', () => {
    expect(transportRadiusLabel(10_000)).toBe('여행 장소 10km 이내');
    expect(transportRadiusLabel(2_500)).toBe('여행 장소 2.5km 이내');
  });

  it('켜지 않은 레이어는 요청하지 않는다', () => {
    expect(requestableTransportLayers(new Set(['fuel_station']), 15)).toEqual(['fuel_station']);
    expect(requestableTransportLayers(new Set(), 15)).toEqual([]);
  });
});

describe('transport freshness', () => {
  it('Map age_seconds에 받은 뒤 흐른 시간을 더하고 음수는 0이다', () => {
    expect(transportFreshnessAgeSeconds({ age_seconds: 600 }, 1_000, 61_000)).toBe(660);
    // 기기 시계가 뒤로 가도 Map 나이 아래로 내려가지 않는다.
    expect(transportFreshnessAgeSeconds({ age_seconds: 600 }, 61_000, 1_000)).toBe(600);
    expect(transportFreshnessAgeSeconds({ age_seconds: -5 }, 0, 0)).toBe(0);
  });

  it('문구', () => {
    expect(transportFreshnessLabel(0)).toBe('방금 갱신');
    expect(transportFreshnessLabel(59)).toBe('방금 갱신');
    expect(transportFreshnessLabel(60)).toBe('1분 전 갱신');
    expect(transportFreshnessLabel(3599)).toBe('59분 전 갱신');
    expect(transportFreshnessLabel(3600)).toBe('1시간 전 갱신');
    expect(transportFreshnessLabel(86_400 * 2 + 5)).toBe('2일 전 갱신');
  });
});

describe('fuel price', () => {
  it('가격과 판매 안 함', () => {
    expect(formatFuelPrice(1689)).toBe('1,689원');
    expect(formatFuelPrice(1688.6)).toBe('1,689원');
    expect(formatFuelPrice(null)).toBe('판매 안 함');
  });

  it('유종 이름', () => {
    expect(fuelProductLabel('diesel', null)).toBe('경유');
    expect(fuelProductLabel('diesel', '자동차용경유')).toBe('자동차용경유');
    expect(fuelProductLabel('hydrogen')).toBe('hydrogen');
  });
});

describe('transport marker id', () => {
  it('왕복한다', () => {
    const id = transportMarkerId('rest_area', 'f_x_place_1');
    expect(id).toBe('transport:rest_area:f_x_place_1');
    expect(parseTransportMarkerId(id)).toEqual({ layer: 'rest_area', featureId: 'f_x_place_1' });
  });

  it('feature 마커·모르는 레이어는 null이다', () => {
    expect(parseTransportMarkerId('me')).toBeNull();
    expect(parseTransportMarkerId('0b6a0c2e-uuid')).toBeNull();
    expect(parseTransportMarkerId('transport:parking:f1')).toBeNull();
    expect(parseTransportMarkerId('transport:airport:')).toBeNull();
  });
});

describe('sortIncidentsByRecency', () => {
  const incident = (id: string, occurred_at: string | null): HighwayIncidentItem => ({
    layer: 'highway_incident',
    feature_id: id,
    category: '99000000',
    marker_icon: 'roadblock',
    marker_color: 'P-13',
    coord: null,
    title: id,
    occurred_at,
  });

  it('최근 순, 시각 없는 항목은 뒤', () => {
    const sorted = sortIncidentsByRecency([
      incident('a', null),
      incident('b', '2026-10-23T08:00:00+09:00'),
      incident('c', '2026-10-23T09:00:00+09:00'),
      incident('d', null),
    ]);
    expect(sorted.map((i) => i.feature_id)).toEqual(['c', 'b', 'a', 'd']);
  });
});

describe('반경 조회 기준점', () => {
  it('키는 5자리 반올림 값이라 미세한 차이·배열 identity와 무관하다', () => {
    const a = [{ lon: 127.0000001, lat: 37.5 }];
    const b = [{ lon: 127.0000004, lat: 37.5000002 }];
    expect(transportNearPointsKey(a)).toBe('127.00000,37.50000');
    expect(transportNearPointsKey(a)).toBe(transportNearPointsKey(b));
    expect(transportNearPointsKey([])).toBe('');
  });

  it('같은 자리(5자리)는 처음 것만 남기고 순서를 지킨다', () => {
    expect(
      dedupeTransportNearPoints([
        { lon: 127.1, lat: 37.1 },
        { lon: 126.9, lat: 37.2 },
        { lon: 127.100001, lat: 37.100001 },
      ]),
    ).toEqual([
      { lon: 127.1, lat: 37.1 },
      { lon: 126.9, lat: 37.2 },
    ]);
  });
});

describe('withUnavailableTransportLayers', () => {
  const ok: TransportLayerResult = {
    layer: 'fuel_station',
    status: 'ok',
    truncated: false,
    items: [],
  };

  it('응답에 빠진 요청 레이어를 불러올 수 없음으로 채운다', () => {
    const results = withUnavailableTransportLayers([ok], ['fuel_station', 'highway_incident']);
    expect(results.map((r) => [r.layer, r.status])).toEqual([
      ['fuel_station', 'ok'],
      ['highway_incident', 'unavailable'],
    ]);
  });

  it('요청 실패(빈 결과)는 요청한 레이어 모두 불러올 수 없음', () => {
    expect(withUnavailableTransportLayers([], ['highway_incident'])).toEqual([
      {
        layer: 'highway_incident',
        status: 'unavailable',
        reason: 'UPSTREAM_UNAVAILABLE',
        truncated: false,
        items: [],
      },
    ]);
  });
});

describe('transportLayerStatusText', () => {
  const base: TransportLayerStatusInput = {
    meta: { layer: 'fuel_station', minZoom: 11 },
    layerStatus: { available: true },
    result: undefined,
    nearMode: true,
    zoom: 7,
    loading: true,
    radiusM: { fuel_station: 10_000 },
    receivedAt: 1_000_000,
    nowMs: 1_000_000 + 120_000,
  };
  const result: TransportLayerResult = {
    layer: 'fuel_station',
    status: 'ok',
    truncated: false,
    items: [],
    freshness: {
      source_collected_at: null,
      loaded_at: '2026-11-17T00:00:00Z',
      age_seconds: 60,
      max_age_seconds: 3600,
      stale: false,
    },
  };

  it('반경 모드는 줌 안내 없이 불러오는 중 → 개수·반경·신선도', () => {
    expect(transportLayerStatusText(base)).toBe(TRANSPORT_STATUS_LOADING_TEXT);
    expect(transportLayerStatusText({ ...base, result })).toBe(
      '0곳 · 여행 장소 10km 이내 · 3분 전 갱신',
    );
    expect(transportLayerStatusText({ ...base, result: { ...result, truncated: true } })).toContain(
      '가까운 곳만 표시',
    );
  });

  it('화면 범위 모드는 최소 줌 아래에서 확대 안내, 반경 문구 없음', () => {
    expect(transportLayerStatusText({ ...base, nearMode: false })).toBe('확대하면 보여요');
    expect(transportLayerStatusText({ ...base, nearMode: false, zoom: 12, result })).toBe(
      '0곳 · 3분 전 갱신',
    );
  });

  it('상태가 불가이거나 결과가 ok가 아니면 불러올 수 없음, 조회 전이면 null', () => {
    expect(transportLayerStatusText({ ...base, layerStatus: { available: false } })).toBe(
      '일시적으로 불러올 수 없음',
    );
    expect(
      transportLayerStatusText({ ...base, result: { ...result, status: 'unavailable' } }),
    ).toBe('일시적으로 불러올 수 없음');
    expect(transportLayerStatusText({ ...base, loading: false })).toBeNull();
  });
});
