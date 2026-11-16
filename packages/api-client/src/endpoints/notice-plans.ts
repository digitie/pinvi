import {
  NoticePlanCopyRequestSchema,
  NoticePlanCopyResponseSchema,
  NoticePlanHighlightsResponseSchema,
  NoticePlanResponseSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { NoticePlanCopyRequest } from '@pinvi/schemas';

export interface NoticePlanListParams {
  category?: string;
  limit?: number;
}

function buildNoticePlanListPath(params: NoticePlanListParams): string {
  const qs = new URLSearchParams();
  if (params.category) {
    qs.set('category', params.category);
  }
  if (params.limit) {
    qs.set('limit', String(params.limit));
  }
  return `/notice-plans${qs.toString() ? `?${qs.toString()}` : ''}`;
}

/** `docs/api/notice-plans.md` 사용자 추천 plan API. */
export const noticePlanApi = (client: ApiClient) => ({
  list: (params: NoticePlanListParams = {}) =>
    client.request(buildNoticePlanListPath(params), {
      method: 'GET',
      schema: z.array(NoticePlanResponseSchema),
    }),

  get: (noticePlanId: string) =>
    client.request(`/notice-plans/${noticePlanId}`, {
      method: 'GET',
      schema: NoticePlanResponseSchema,
    }),

  /** 기간 중 축제·행사 + 주변 큐레이션(kor-travel-map). Map 장애 구역은 `unavailable`. */
  highlights: (noticePlanId: string, opts?: { signal?: AbortSignal }) =>
    client.request(`/notice-plans/${noticePlanId}/highlights`, {
      method: 'GET',
      schema: NoticePlanHighlightsResponseSchema,
      signal: opts?.signal,
    }),

  copy: (noticePlanId: string, body: NoticePlanCopyRequest, opts?: { signal?: AbortSignal }) =>
    client.request(`/notice-plans/${noticePlanId}/copy`, {
      method: 'POST',
      body: JSON.stringify(NoticePlanCopyRequestSchema.parse(body)),
      schema: NoticePlanCopyResponseSchema,
      // 복사 다이얼로그를 닫으면 취소한다 — 방치하면 사용자가 닫은 뒤 여행이 생긴다.
      signal: opts?.signal,
    }),
});
