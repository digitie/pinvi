import { describe, expect, it } from 'vitest';
import { TransportMarkersInBoundsResponseSchema } from './transport';

/** API(`apps/api/app/schemas/transport.py`)가 실제로 내보내는 모양 — pydantic은 UTC를 `Z`로 쓴다. */
const payload = {
  bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
  zoom: 12,
  layers: [
    {
      layer: 'airport',
      status: 'ok',
      reason: null,
      freshness: {
        source_collected_at: null,
        loaded_at: '2026-10-23T00:05:00Z',
        age_seconds: 600,
        max_age_seconds: 691200,
        stale: false,
      },
      fuel_price_freshness: null,
      truncated: false,
      items: [
        {
          layer: 'airport',
          feature_id: 'f_x_place_a1',
          category: '06030100',
          marker_icon: 'airport',
          marker_color: 'P-10',
          coord: { lon: 126.79, lat: 37.55 },
          distance_m: null,
          name: '김포국제공항',
          name_english: 'Gimpo International Airport',
          iata_code: 'GMP',
          icao_code: 'RKSS',
          municipality: null,
          address: { road: null, jibun: null },
        },
      ],
    },
    {
      layer: 'fuel_station',
      status: 'unavailable',
      reason: 'NOT_LOADED',
      freshness: null,
      fuel_price_freshness: null,
      truncated: false,
      items: [],
    },
  ],
};

describe('TransportMarkersInBoundsResponseSchema', () => {
  it('API 응답(UTC Z·null 필드)을 받는다', () => {
    const parsed = TransportMarkersInBoundsResponseSchema.parse(payload);
    expect(parsed.layers[0]?.items[0]?.layer).toBe('airport');
    expect(parsed.layers[1]?.reason).toBe('NOT_LOADED');
  });

  it('모르는 레이어는 거부한다', () => {
    const broken = structuredClone(payload);
    broken.layers[0]!.layer = 'parking';
    expect(TransportMarkersInBoundsResponseSchema.safeParse(broken).success).toBe(false);
  });
});
