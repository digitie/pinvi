import { GeoCandidateListSchema, PlaceSearchResponseSchema } from '@pinvi/schemas';
import type { CoordSource } from '@pinvi/schemas';
import type { ApiClient } from '../client';

/** `docs/integrations/kor-travel-geo.md` — kor-travel-geo v2 proxy API. */
export const geoApi = (client: ApiClient) => ({
  /**
   * 좌표 → 주소/행정구역. `coordSource`는 이 좌표가 무엇인지 서버에 알린다 —
   * `'map_pick'`(기본)은 사용자가 지도에서 고른 지점이고, `'device'`는 단말 측위 결과다.
   * `'device'`는 개인위치정보 수집이라 서버가 위치 동의를 요구한다(403 `LOCATION_CONSENT_REQUIRED`).
   */
  reverse: (
    params: {
      lon: number;
      lat: number;
      radiusM?: number;
      coordSource?: CoordSource;
    },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('lon', String(params.lon));
    qs.set('lat', String(params.lat));
    if (params.radiusM != null) qs.set('radius_m', String(params.radiusM));
    if (params.coordSource != null) qs.set('coord_source', params.coordSource);
    return client.request(`/geo/reverse?${qs.toString()}`, {
      method: 'GET',
      schema: GeoCandidateListSchema,
      signal: opts?.signal,
    });
  },

  /**
   * 통합 검색(source-tagged) — feature + address + 내 POI + Kakao/Naver Local(표시 전용).
   * `docs/api/search.md`(ADR-054). `lat`/`lon`은 "내 주변 검색"(위치정보 제3자 제공, §9)일 때만.
   */
  searchPlaces: (
    params: { q: string; limit?: number; lat?: number; lon?: number },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('q', params.q);
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.lat != null) qs.set('lat', String(params.lat));
    if (params.lon != null) qs.set('lon', String(params.lon));
    return client.request(`/search?${qs.toString()}`, {
      method: 'GET',
      schema: PlaceSearchResponseSchema,
      signal: opts?.signal,
    });
  },
});
