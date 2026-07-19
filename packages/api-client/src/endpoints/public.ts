import {
  PublicBeachListSchema,
  PublicBeachViewSchema,
  PublicFestivalMonthlySchema,
  PublicFestivalViewSchema,
  PublicMapMarkerLayerSchema,
} from '@pinvi/schemas';
import type {
  PublicBeachList,
  PublicFestivalMonthly,
} from '@pinvi/schemas';
import type { ApiClient } from '../client';

export interface PublicBeachListParams {
  sido_code?: string;
  sigungu_code?: string;
  q?: string;
  page_size?: number;
  cursor?: string;
}

export interface PublicFestivalMonthlyParams {
  year?: number;
  month?: number;
  sido_code?: string;
  sigungu_code?: string;
  page_size?: number;
  cursor?: string;
  include_months?: boolean;
}

export interface PublicMarkerParams {
  min_lon?: number;
  min_lat?: number;
  max_lon?: number;
  max_lat?: number;
  sido_code?: string;
  sigungu_code?: string;
  max_items?: number;
}

export interface PublicFestivalMarkerParams extends Omit<PublicMarkerParams, 'sido_code' | 'sigungu_code'> {
  year?: number;
  month?: number;
}

export interface PublicPage<T> {
  data: T;
  cursor: string | null;
  has_more: boolean;
  total: number | null;
}

function buildPath(path: string, params: object): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      qs.set(key, String(value));
    }
  }
  return `${path}${qs.toString() ? `?${qs.toString()}` : ''}`;
}

/** `docs/api/public.md` — 인증 없는 해수욕장/축제 공개 API. */
export const publicApi = (client: ApiClient) => ({
  beaches: async (params: PublicBeachListParams = {}): Promise<PublicPage<PublicBeachList>> => {
    const envelope = await client.requestEnvelope(buildPath('/public/beaches', params), {
      method: 'GET',
      schema: PublicBeachListSchema,
    });
    return {
      data: envelope.data,
      cursor: envelope.meta?.cursor ?? null,
      has_more: envelope.meta?.has_more ?? false,
      total: envelope.meta?.total ?? null,
    };
  },

  beachMarkers: (params: PublicMarkerParams = {}) =>
    client.request(buildPath('/public/beaches/map-markers', params), {
      method: 'GET',
      schema: PublicMapMarkerLayerSchema,
    }),

  beach: (featureId: string) =>
    client.request(`/public/beaches/${featureId}`, {
      method: 'GET',
      schema: PublicBeachViewSchema,
    }),

  festivalsMonthly: async (
    params: PublicFestivalMonthlyParams = {},
  ): Promise<PublicPage<PublicFestivalMonthly>> => {
    const envelope = await client.requestEnvelope(buildPath('/public/festivals/monthly', params), {
      method: 'GET',
      schema: PublicFestivalMonthlySchema,
    });
    return {
      data: envelope.data,
      cursor: envelope.meta?.cursor ?? null,
      has_more: envelope.meta?.has_more ?? false,
      total: envelope.meta?.total ?? null,
    };
  },

  festivalMarkers: (params: PublicFestivalMarkerParams = {}) =>
    client.request(buildPath('/public/festivals/map-markers', params), {
      method: 'GET',
      schema: PublicMapMarkerLayerSchema,
    }),

  festival: (featureId: string) =>
    client.request(`/public/festivals/${featureId}`, {
      method: 'GET',
      schema: PublicFestivalViewSchema,
    }),
});
