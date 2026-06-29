import {
  DownloadUrlResponseSchema,
  AttachmentLibraryPageSchema,
  TripAttachmentCreateSchema,
  TripAttachmentResponseSchema,
  TripCommentCreateSchema,
  TripCommentResponseSchema,
  TripCompanionInviteSchema,
  TripCompanionResponseSchema,
  TripCopyRequestSchema,
  TripCopyResponseSchema,
  TripCreateSchema,
  TripDayCreateSchema,
  TripDayOptimizeRequestSchema,
  TripDayOptimizeResponseSchema,
  TripDayResponseSchema,
  TripDayUpdateSchema,
  TripDeleteRequestSchema,
  TripDistanceMatrixResponseSchema,
  TripResponseSchema,
  TripSharedViewSchema,
  TripShareLinkCreateSchema,
  TripShareLinkResponseSchema,
  TripUpdateSchema,
  TripViewSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type {
  TripAttachmentCreate,
  TripCommentCreate,
  TripCompanionInvite,
  TripCopyRequest,
  TripCreate,
  TripDayCreate,
  TripDayOptimizeRequest,
  TripDayUpdate,
  TripDeleteRequest,
  TripShareLinkCreate,
  TripUpdate,
} from '@pinvi/schemas';

export type TripBucket = 'future' | 'past' | 'all';
export type TripListSort = '-updated_at' | 'start_date' | '-start_date' | 'title';

export interface TripListParams {
  bucket?: TripBucket;
  q?: string;
  status?: 'draft' | 'planned' | 'in_progress' | 'completed' | 'archived';
  visibility?: 'private' | 'unlisted' | 'public';
  date_from?: string;
  date_to?: string;
  sort?: TripListSort;
  limit?: number;
  cursor?: string;
}

export interface TripListPage {
  items: z.infer<typeof TripResponseSchema>[];
  cursor: string | null;
  has_more: boolean;
}

function buildTripListPath(params: TripListParams): string {
  const qs = new URLSearchParams();
  if (params.bucket) {
    qs.set('bucket', params.bucket);
  }
  if (params.q) {
    qs.set('q', params.q);
  }
  if (params.status) {
    qs.set('status', params.status);
  }
  if (params.visibility) {
    qs.set('visibility', params.visibility);
  }
  if (params.date_from) {
    qs.set('date_from', params.date_from);
  }
  if (params.date_to) {
    qs.set('date_to', params.date_to);
  }
  if (params.sort) {
    qs.set('sort', params.sort);
  }
  if (params.limit) {
    qs.set('limit', String(params.limit));
  }
  if (params.cursor) {
    qs.set('cursor', params.cursor);
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

  listPage: async (params: TripListParams = {}): Promise<TripListPage> => {
    const envelope = await client.requestEnvelope(buildTripListPath(params), {
      method: 'GET',
      schema: z.array(TripResponseSchema),
    });
    return {
      items: envelope.data,
      cursor: envelope.meta?.cursor ?? null,
      has_more: envelope.meta?.has_more ?? false,
    };
  },

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

  listFiles: (tripId: string, params: { page?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/trips/${tripId}/files${qs.toString() ? `?${qs.toString()}` : ''}`, {
      method: 'GET',
      schema: AttachmentLibraryPageSchema,
    });
  },

  update: (tripId: string, version: number, body: TripUpdate) =>
    client.request(`/trips/${tripId}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(TripUpdateSchema.parse(body)),
      schema: TripResponseSchema,
    }),

  delete: (tripId: string, body: TripDeleteRequest = { mode: 'soft_delete' }) =>
    client.requestNoContent(`/trips/${tripId}`, {
      method: 'DELETE',
      body: JSON.stringify(TripDeleteRequestSchema.parse(body)),
    }),

  copy: (tripId: string, body: TripCopyRequest = { scope: 'all', date_shift_days: 0 }) =>
    client.request(`/trips/${tripId}/copy`, {
      method: 'POST',
      body: JSON.stringify(TripCopyRequestSchema.parse(body)),
      schema: TripCopyResponseSchema,
    }),

  createDay: (tripId: string, body: TripDayCreate) =>
    client.request(`/trips/${tripId}/days`, {
      method: 'POST',
      body: JSON.stringify(TripDayCreateSchema.parse(body)),
      schema: TripDayResponseSchema,
    }),

  updateDay: (tripId: string, dayIndex: number, version: number, body: TripDayUpdate) =>
    client.request(`/trips/${tripId}/days/${dayIndex}`, {
      method: 'PATCH',
      headers: { 'If-Match': String(version) },
      body: JSON.stringify(TripDayUpdateSchema.parse(body)),
      schema: TripDayResponseSchema,
    }),

  deleteDay: (tripId: string, dayIndex: number, version: number) =>
    client.requestNoContent(`/trips/${tripId}/days/${dayIndex}`, {
      method: 'DELETE',
      headers: { 'If-Match': String(version) },
    }),

  getShared: (tripId: string, token: string) =>
    client.request(`/trips/${tripId}/shared/${token}`, {
      method: 'GET',
      schema: TripSharedViewSchema,
    }),

  listAttachments: (tripId: string) =>
    client.request(`/trips/${tripId}/attachments`, {
      method: 'GET',
      schema: z.array(TripAttachmentResponseSchema),
    }),

  createAttachment: (tripId: string, body: TripAttachmentCreate) =>
    client.request(`/trips/${tripId}/attachments`, {
      method: 'POST',
      body: JSON.stringify(TripAttachmentCreateSchema.parse(body)),
      schema: TripAttachmentResponseSchema,
    }),

  deleteAttachment: (tripId: string, attachmentId: string) =>
    client.requestNoContent(`/trips/${tripId}/attachments/${attachmentId}`, {
      method: 'DELETE',
    }),

  attachmentDownloadUrl: (tripId: string, attachmentId: string) =>
    client.request(`/trips/${tripId}/attachments/${attachmentId}/download-url`, {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  listDayAttachments: (tripId: string, dayIndex: number) =>
    client.request(`/trips/${tripId}/days/${dayIndex}/attachments`, {
      method: 'GET',
      schema: z.array(TripAttachmentResponseSchema),
    }),

  createDayAttachment: (tripId: string, dayIndex: number, body: TripAttachmentCreate) =>
    client.request(`/trips/${tripId}/days/${dayIndex}/attachments`, {
      method: 'POST',
      body: JSON.stringify(TripAttachmentCreateSchema.parse(body)),
      schema: TripAttachmentResponseSchema,
    }),

  deleteDayAttachment: (tripId: string, dayIndex: number, attachmentId: string) =>
    client.requestNoContent(`/trips/${tripId}/days/${dayIndex}/attachments/${attachmentId}`, {
      method: 'DELETE',
    }),

  dayAttachmentDownloadUrl: (tripId: string, dayIndex: number, attachmentId: string) =>
    client.request(
      `/trips/${tripId}/days/${dayIndex}/attachments/${attachmentId}/download-url`,
      {
        method: 'GET',
        schema: DownloadUrlResponseSchema,
      }
    ),

  listPoiAttachments: (tripId: string, poiId: string) =>
    client.request(`/trips/${tripId}/pois/${poiId}/attachments`, {
      method: 'GET',
      schema: z.array(TripAttachmentResponseSchema),
    }),

  createPoiAttachment: (tripId: string, poiId: string, body: TripAttachmentCreate) =>
    client.request(`/trips/${tripId}/pois/${poiId}/attachments`, {
      method: 'POST',
      body: JSON.stringify(TripAttachmentCreateSchema.parse(body)),
      schema: TripAttachmentResponseSchema,
    }),

  deletePoiAttachment: (tripId: string, poiId: string, attachmentId: string) =>
    client.requestNoContent(`/trips/${tripId}/pois/${poiId}/attachments/${attachmentId}`, {
      method: 'DELETE',
    }),

  poiAttachmentDownloadUrl: (tripId: string, poiId: string, attachmentId: string) =>
    client.request(`/trips/${tripId}/pois/${poiId}/attachments/${attachmentId}/download-url`, {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  getDistanceMatrix: (tripId: string, dayIndex: number) =>
    client.request(`/trips/${tripId}/days/${dayIndex}/distance-matrix`, {
      method: 'GET',
      schema: TripDistanceMatrixResponseSchema,
    }),

  optimizeDay: (
    tripId: string,
    dayIndex: number,
    body: TripDayOptimizeRequest = { strategy: 'two_opt', persist: false },
  ) =>
    client.request(`/trips/${tripId}/days/${dayIndex}/optimize`, {
      method: 'POST',
      body: JSON.stringify(TripDayOptimizeRequestSchema.parse(body)),
      schema: TripDayOptimizeResponseSchema,
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
