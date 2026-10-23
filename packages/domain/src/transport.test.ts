import { describe, expect, it } from 'vitest';
import type { HighwayIncidentItem, TransportLayer } from '@pinvi/schemas';
import {
  formatFuelPrice,
  fuelProductLabel,
  parseTransportMarkerId,
  requestableTransportLayers,
  sortIncidentsByRecency,
  transportFreshnessAgeSeconds,
  transportFreshnessLabel,
  transportMarkerId,
} from './transport';

describe('requestableTransportLayers', () => {
  const all = new Set<TransportLayer>(['fuel_station', 'rest_area', 'highway_incident', 'airport']);

  it('줌이 낮으면 최소 줌 이상인 레이어만 요청한다', () => {
    expect(requestableTransportLayers(all, 6)).toEqual(['airport']);
    expect(requestableTransportLayers(all, 8)).toEqual(['rest_area', 'highway_incident', 'airport']);
    expect(requestableTransportLayers(all, 11)).toEqual([
      'fuel_station',
      'rest_area',
      'highway_incident',
      'airport',
    ]);
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
