import { describe, expect, it } from 'vitest';
import type { WeatherMarkersInBoundsResponse } from '@pinvi/schemas';
import { toWeatherPoints } from '@/components/map/FeatureMapView';

/**
 * `FeatureMapView`는 VWorld/MapLibre 의존성 때문에 컴포넌트 전체를 렌더 테스트하지
 * 않는다(N150 Playwright e2e 전용, ADR-051). 여기서는 T-368이 새로 도입한 순수
 * 변환 함수(`toWeatherPoints`)만 검증한다 — `kor-travel-weather` 응답 → 지도 point.
 */
describe('toWeatherPoints', () => {
  it('kor-travel-weather 응답을 WeatherMapPoint로 변환한다', () => {
    const response: WeatherMarkersInBoundsResponse = {
      items: [
        {
          location_id: 'loc-1',
          name: '중구',
          coord: { lon: 127.0, lat: 37.5 },
          temperature_c: 21.5,
          condition: 'rainy',
          provider: 'python-kma-api',
        },
      ],
      zoom: 10,
      bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
    };

    const points = toWeatherPoints(response);

    expect(points).toEqual([
      {
        id: 'weather:loc-1',
        lngLat: [127.0, 37.5],
        kind: 'weather',
        locationId: 'loc-1',
        title: '중구',
        temperatureC: 21.5,
        condition: 'rainy',
        provider: 'python-kma-api',
      },
    ]);
  });

  it('provider가 없으면 null로 정규화한다', () => {
    const response: WeatherMarkersInBoundsResponse = {
      items: [
        {
          location_id: 'loc-2',
          name: '해운대',
          coord: { lon: 129.16, lat: 35.16 },
          temperature_c: 24.0,
          condition: 'cloudy',
          provider: null,
        },
      ],
      zoom: 12,
      bbox: { lng_min: 129.0, lat_min: 35.0, lng_max: 129.3, lat_max: 35.3 },
    };

    const points = toWeatherPoints(response);

    expect(points[0]?.provider).toBeNull();
  });

  it('빈 목록이면 빈 배열을 반환한다', () => {
    const response: WeatherMarkersInBoundsResponse = {
      items: [],
      zoom: 10,
      bbox: { lng_min: 126.9, lat_min: 37.4, lng_max: 127.1, lat_max: 37.6 },
    };

    expect(toWeatherPoints(response)).toEqual([]);
  });
});
