import {
  FeatureDetailSchema,
  FeatureRequestCreateSchema,
  FeatureRequestResponseSchema,
  FeatureSummarySchema,
  FeatureWeatherCardSchema,
  FeaturesInBoundsResponseSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type {
  FeatureKind,
  FeatureRequestCreate,
} from '@tripmate/schemas';

/** `docs/api/features.md` — Sprint 4 (v0.1.0 게이트). */
export const featureApi = (client: ApiClient) => ({
  /**
   * viewport 내 feature + cluster 응답. zoom별 라이브러리 측 클러스터링.
   * bbox format: `lng_min,lat_min,lng_max,lat_max`.
   */
  inBounds: (params: {
    bbox: string;
    zoom: number;
    kinds?: FeatureKind[];
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    qs.set('bbox', params.bbox);
    qs.set('zoom', String(params.zoom));
    if (params.kinds) for (const k of params.kinds) qs.append('kinds', k);
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/features/in-bounds?${qs.toString()}`, {
      method: 'GET',
      schema: FeaturesInBoundsResponseSchema,
    });
  },

  /** 반경 검색. location_audit 미들웨어가 좌표 query 자동 감지 + chain 적재. */
  nearby: (params: {
    lat: number;
    lng: number;
    radius_m: number;
    kinds?: FeatureKind[];
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    qs.set('lat', String(params.lat));
    qs.set('lng', String(params.lng));
    qs.set('radius_m', String(params.radius_m));
    if (params.kinds) for (const k of params.kinds) qs.append('kinds', k);
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/features/nearby?${qs.toString()}`, {
      method: 'GET',
      schema: z.array(FeatureSummarySchema),
    });
  },

  /** 자유 텍스트 검색 (FTS5/pg_trgm). */
  search: (params: {
    q: string;
    kinds?: FeatureKind[];
    bbox?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    qs.set('q', params.q);
    if (params.kinds) for (const k of params.kinds) qs.append('kinds', k);
    if (params.bbox) qs.set('bbox', params.bbox);
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/features/search?${qs.toString()}`, {
      method: 'GET',
      schema: z.array(FeatureSummarySchema),
    });
  },

  /** feature 1건 상세. */
  get: (featureId: string) =>
    client.request(`/features/${featureId}`, {
      method: 'GET',
      schema: FeatureDetailSchema,
    }),

  /** KMA 시간축 weather card. */
  weather: (featureId: string) =>
    client.request(`/features/${featureId}/weather`, {
      method: 'GET',
      schema: FeatureWeatherCardSchema,
    }),

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
