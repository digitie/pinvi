import {
  PoiCreateSchema,
  PoiReorderRequestSchema,
  PoiResponseSchema,
  PoiUpdateSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { PoiCreate, PoiReorderRequest, PoiUpdate } from '@tripmate/schemas';

/** `docs/api/pois.md` 정본 POI API. */
export const poiApi = (client: ApiClient) => ({
  create: (tripId: string, body: PoiCreate) =>
    client.request(`/trips/${tripId}/pois`, {
      method: 'POST',
      body: JSON.stringify(PoiCreateSchema.parse(body)),
      schema: PoiResponseSchema,
    }),

  update: (tripId: string, poiId: string, version: number, body: PoiUpdate) =>
    client.request(`/trips/${tripId}/pois/${poiId}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(PoiUpdateSchema.parse(body)),
      schema: PoiResponseSchema,
    }),

  delete: (tripId: string, poiId: string) =>
    client.requestNoContent(`/trips/${tripId}/pois/${poiId}`, {
      method: 'DELETE',
    }),

  reorder: (tripId: string, body: PoiReorderRequest) =>
    client.request(`/trips/${tripId}/pois/reorder`, {
      method: 'POST',
      body: JSON.stringify(PoiReorderRequestSchema.parse(body)),
      schema: z.array(PoiResponseSchema),
    }),
});
