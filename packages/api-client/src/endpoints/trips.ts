import {
  TripCommentCreateSchema,
  TripCommentResponseSchema,
  TripCompanionInviteSchema,
  TripCompanionResponseSchema,
  TripCreateSchema,
  TripResponseSchema,
  TripShareLinkCreateSchema,
  TripShareLinkResponseSchema,
  TripUpdateSchema,
  TripViewSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type {
  TripCommentCreate,
  TripCompanionInvite,
  TripCreate,
  TripShareLinkCreate,
  TripUpdate,
} from '@tripmate/schemas';

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
      schema: TripViewSchema,
    }),

  update: (tripId: string, version: number, body: TripUpdate) =>
    client.request(`/trips/${tripId}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(TripUpdateSchema.parse(body)),
      schema: TripResponseSchema,
    }),

  inviteMember: (tripId: string, body: TripCompanionInvite) =>
    client.request(`/trips/${tripId}/members`, {
      method: 'POST',
      body: JSON.stringify(TripCompanionInviteSchema.parse(body)),
      schema: TripCompanionResponseSchema,
    }),

  removeMember: (tripId: string, companionId: string) =>
    client.requestNoContent(`/trips/${tripId}/members/${companionId}`, {
      method: 'DELETE',
    }),

  listComments: (tripId: string, limit = 50) =>
    client.request(`/trips/${tripId}/comments?limit=${limit}`, {
      method: 'GET',
      schema: z.array(TripCommentResponseSchema),
    }),

  createComment: (tripId: string, body: TripCommentCreate) =>
    client.request(`/trips/${tripId}/comments`, {
      method: 'POST',
      body: JSON.stringify(TripCommentCreateSchema.parse(body)),
      schema: TripCommentResponseSchema,
    }),

  deleteComment: (tripId: string, commentId: string) =>
    client.requestNoContent(`/trips/${tripId}/comments/${commentId}`, {
      method: 'DELETE',
    }),

  createShareToken: (tripId: string, body: TripShareLinkCreate) =>
    client.request(`/trips/${tripId}/share-tokens`, {
      method: 'POST',
      body: JSON.stringify(TripShareLinkCreateSchema.parse(body)),
      schema: TripShareLinkResponseSchema,
    }),

  revokeShareToken: (tripId: string, shareId: string) =>
    client.requestNoContent(`/trips/${tripId}/share-tokens/${shareId}`, {
      method: 'DELETE',
    }),
});
