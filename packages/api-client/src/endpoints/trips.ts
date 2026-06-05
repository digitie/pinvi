import {
  TripCreateSchema,
  TripResponseSchema,
  TripUpdateSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { TripCreate, TripUpdate } from '@tripmate/schemas';

export type TripBucket = 'future' | 'past' | 'all';

export interface TripListParams {
  bucket?: TripBucket;
  limit?: number;
}

function buildTripListPath(params: TripListParams): string {
  const qs = new URLSearchParams();
  if (params.bucket && params.bucket !== 'all') {
    qs.set('bucket', params.bucket);
  }
  if (params.limit) {
    qs.set('limit', String(params.limit));
  }
  return `/trips${qs.toString() ? `?${qs.toString()}` : ''}`;
}

/** `docs/api/trips.md` 사용자 Trip API. */
export const tripApi = (client: ApiClient) => ({
  list: (params: TripListParams = {}) =>
    client.request(buildTripListPath(params), {
      method: 'GET',
      schema: z.array(TripResponseSchema),
    }),

  create: (body: TripCreate) =>
    client.request('/trips', {
      method: 'POST',
      body: JSON.stringify(TripCreateSchema.parse(body)),
      schema: TripResponseSchema,
    }),

  get: (tripId: string) =>
    client.request(`/trips/${tripId}`, {
      method: 'GET',
      schema: TripResponseSchema,
    }),

  update: (tripId: string, version: number, body: TripUpdate) =>
    client.request(`/trips/${tripId}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(TripUpdateSchema.parse(body)),
      schema: TripResponseSchema,
    }),
});
