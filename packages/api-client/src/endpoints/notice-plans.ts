import {
  NoticePlanCopyRequestSchema,
  NoticePlanCopyResponseSchema,
  NoticePlanResponseSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { NoticePlanCopyRequest } from '@tripmate/schemas';

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

  copy: (noticePlanId: string, body: NoticePlanCopyRequest) =>
    client.request(`/notice-plans/${noticePlanId}/copy`, {
      method: 'POST',
      body: JSON.stringify(NoticePlanCopyRequestSchema.parse(body)),
      schema: NoticePlanCopyResponseSchema,
    }),
});
