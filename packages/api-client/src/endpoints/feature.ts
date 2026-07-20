import {
  FeatureCategorySchema,
  FeatureDetailSchema,
  FeatureRequestCreateSchema,
  FeatureRequestResponseSchema,
  FeatureSummarySchema,
  FeatureWeatherCardSchema,
  FeaturesInBoundsResponseSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { FeatureKind, FeatureRequestCreate } from '@pinvi/schemas';

/** `docs/api/features.md` — Sprint 4 (v0.1.0 게이트). */
export const featureApi = (client: ApiClient) => ({
  /**
   * viewport 내 feature + cluster 응답. zoom별 라이브러리 측 클러스터링.
   * bbox format: `lng_min,lat_min,lng_max,lat_max`.
   */
  inBounds: (
    params: {
      bbox: string;
      zoom: number;
      kinds?: FeatureKind[];
      category?: string;
      clusterUnit?: string;
      limit?: number;
    },
    // viewport pan은 빠르게 superseded되므로 호출부가 AbortSignal을 넘겨 직전 요청을
    // 취소할 수 있다. signal은 client.fetch가 upstream fetch로 그대로 전달한다.
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('bbox', params.bbox);
    qs.set('zoom', String(params.zoom));
    if (params.kinds) for (const k of params.kinds) qs.append('kinds', k);
    if (params.category) qs.set('category', params.category);
    if (params.clusterUnit) qs.set('cluster_unit', params.clusterUnit);
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/features/in-bounds?${qs.toString()}`, {
      method: 'GET',
      schema: FeaturesInBoundsResponseSchema,
      signal: opts?.signal,
    });
  },

  /** 반경 검색 (distance_m 포함). location_audit 미들웨어가 좌표 query 자동 적재. */
  nearby: (
    params: {
      lat: number;
      lon: number;
      radius_m: number;
      kinds?: FeatureKind[];
      category?: string;
      limit?: number;
    },
    opts?: { signal?: AbortSignal },
  ) => {
    const qs = new URLSearchParams();
    qs.set('lat', String(params.lat));
    qs.set('lon', String(params.lon));
    qs.set('radius_m', String(params.radius_m));
    if (params.kinds) for (const k of params.kinds) qs.append('kinds', k);
    if (params.category) qs.set('category', params.category);
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/features/nearby?${qs.toString()}`, {
      method: 'GET',
      schema: z.array(FeatureSummarySchema),
      signal: opts?.signal,
    });
  },

  // NOTE: 자유 텍스트 feature 검색은 통합 `GET /search`(geoApi.searchPlaces, ADR-054)로 이전됐다.
  // `/features/search`는 삭제됐고 feature는 통합 검색의 source=feature 행으로 나온다.

  /** feature 1건 상세. */
  get: (featureId: string) =>
    client.request(`/features/${featureId}`, {
      method: 'GET',
      schema: FeatureDetailSchema,
    }),

  /** KMA 시간축 weather card. */
  weather: (featureId: string, params: { asof?: string | null } = {}) => {
    const qs = new URLSearchParams();
    if (params.asof) qs.set('asof', params.asof);
    return client.request(`/features/${featureId}/weather${qs.toString() ? `?${qs}` : ''}`, {
      method: 'GET',
      schema: FeatureWeatherCardSchema,
    });
  },

  /** 카테고리 카탈로그 (마커 범례 / 필터 칩). 저빈도 → 긴 staleTime 권장. */
  categories: (params: { activeOnly?: boolean } = {}) => {
    const qs = new URLSearchParams();
    if (params.activeOnly === false) qs.set('active_only', 'false');
    const path = `/features/categories${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, { method: 'GET', schema: z.array(FeatureCategorySchema) });
  },

  /** feature 요청 큐 등록 (Sprint 6 Admin 검토). */
  request: (body: FeatureRequestCreate) =>
    client.request('/features/requests', {
      method: 'POST',
      body: JSON.stringify(FeatureRequestCreateSchema.parse(body)),
      schema: FeatureRequestResponseSchema,
    }),

  /** feature 요청 큐 상세. */
  getRequest: (requestId: string) =>
    client.request(`/features/requests/${requestId}`, {
      method: 'GET',
      schema: FeatureRequestResponseSchema,
    }),
});
