import { WeatherMarkersInBoundsResponseSchema } from '@pinvi/schemas';
import type { ApiClient } from '../client';

/**
 * 지도 weather marker — `kor-travel-weather` 직접 조회(ADR-068, T-368).
 *
 * `featureApi.inBounds`와 별개 경로다 — feature가 아니라 `kor-travel-weather`의
 * location을 노출하므로 완전히 분리된 계약을 쓴다.
 */
export const weatherApi = (client: ApiClient) => ({
  /**
   * viewport 내 weather marker(위치+현재 온도) 목록. bbox format:
   * `lng_min,lat_min,lng_max,lat_max` — `featureApi.inBounds`와 동일.
   */
  markersInBounds: (
    params: { bbox: string; zoom: number; limit?: number },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('bbox', params.bbox);
    qs.set('zoom', String(params.zoom));
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/weather/markers-in-bounds?${qs.toString()}`, {
      method: 'GET',
      schema: WeatherMarkersInBoundsResponseSchema,
      signal: opts?.signal,
    });
  },
});
