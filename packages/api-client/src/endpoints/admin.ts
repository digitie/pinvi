import {
  AdminActionRequestSchema,
  AdminAuditEntrySchema,
  AdminBackupRestoreRequestSchema,
  AdminBackupRestoreRunSchema,
  AdminBackupSnapshotRequestSchema,
  AdminBackupSnapshotSchema,
  AdminChainVerifySchema,
  AdminEmailEntrySchema,
  AdminPagedResponseSchema,
  AdminPoiDetailSchema,
  AdminPoiLinkStatusRequestSchema,
  AdminPoiPagedResponseSchema,
  AdminTripDetailSchema,
  AdminTripPagedResponseSchema,
  AdminTripStatusRequestSchema,
  AdminUserDetailSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

/** `docs/api/admin.md` Sprint 3 범위. */
export const adminApi = (client: ApiClient) => ({
  listUsers: (params: { page?: number; limit?: number; status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.status) qs.set('status_filter', params.status);
    if (params.q) qs.set('q', params.q);
    const path = `/admin/users${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminPagedResponseSchema,
    });
  },

  getUser: (userId: string) =>
    client.request(`/admin/users/${userId}`, {
      method: 'GET',
      schema: AdminUserDetailSchema,
    }),

  revealUserPii: (userId: string, body: z.infer<typeof AdminActionRequestSchema>) =>
    client.request(`/admin/users/${userId}/reveal-pii`, {
      method: 'POST',
      body: JSON.stringify(AdminActionRequestSchema.parse(body)),
      schema: AdminUserDetailSchema,
    }),

  forceVerify: (userId: string, body: z.infer<typeof AdminActionRequestSchema>) =>
    client.request(`/admin/users/${userId}/force-verify`, {
      method: 'POST',
      body: JSON.stringify(AdminActionRequestSchema.parse(body)),
      schema: AdminUserDetailSchema,
    }),

  disableUser: (userId: string, body: z.infer<typeof AdminActionRequestSchema>) =>
    client.request(`/admin/users/${userId}/disable`, {
      method: 'POST',
      body: JSON.stringify(AdminActionRequestSchema.parse(body)),
      schema: AdminUserDetailSchema,
    }),

  listTrips: (
    params: {
      page?: number;
      limit?: number;
      status?: string;
      visibility?: string;
      ownerUserId?: string;
      q?: string;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.status) qs.set('status_filter', params.status);
    if (params.visibility) qs.set('visibility_filter', params.visibility);
    if (params.ownerUserId) qs.set('owner_user_id', params.ownerUserId);
    if (params.q) qs.set('q', params.q);
    const path = `/admin/trips${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminTripPagedResponseSchema,
    });
  },

  getTrip: (tripId: string) =>
    client.request(`/admin/trips/${tripId}`, {
      method: 'GET',
      schema: AdminTripDetailSchema,
    }),

  updateTripStatus: (
    tripId: string,
    body: z.infer<typeof AdminTripStatusRequestSchema>,
  ) =>
    client.request(`/admin/trips/${tripId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(AdminTripStatusRequestSchema.parse(body)),
      schema: AdminTripDetailSchema,
    }),

  listPois: (
    params: {
      page?: number;
      limit?: number;
      tripId?: string;
      hasBrokenLink?: boolean;
      q?: string;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.tripId) qs.set('trip_id', params.tripId);
    if (params.hasBrokenLink !== undefined) {
      qs.set('has_broken_link', String(params.hasBrokenLink));
    }
    if (params.q) qs.set('q', params.q);
    const path = `/admin/pois${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminPoiPagedResponseSchema,
    });
  },

  getPoi: (poiId: string) =>
    client.request(`/admin/pois/${poiId}`, {
      method: 'GET',
      schema: AdminPoiDetailSchema,
    }),

  updatePoiLinkStatus: (
    poiId: string,
    body: z.infer<typeof AdminPoiLinkStatusRequestSchema>,
  ) =>
    client.request(`/admin/pois/${poiId}/link-status`, {
      method: 'PATCH',
      body: JSON.stringify(AdminPoiLinkStatusRequestSchema.parse(body)),
      schema: AdminPoiDetailSchema,
    }),

  listAudit: (limit = 50) =>
    client.request(`/admin/audit?limit=${limit}`, {
      method: 'GET',
      schema: z.array(AdminAuditEntrySchema),
    }),

  verifyChain: () =>
    client.request('/admin/audit/verify-chain', {
      method: 'GET',
      schema: AdminChainVerifySchema,
    }),

  listEmails: (params: { status?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status_filter', params.status);
    if (params.limit) qs.set('limit', String(params.limit));
    const path = `/admin/emails${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: z.array(AdminEmailEntrySchema),
    });
  },

  resendEmail: (emailId: string) =>
    client.request(`/admin/emails/${emailId}/resend`, {
      method: 'POST',
      schema: AdminEmailEntrySchema,
    }),

  listBackupSnapshots: (limit = 50) =>
    client.request(`/admin/backup/snapshots?limit=${limit}`, {
      method: 'GET',
      schema: z.array(AdminBackupSnapshotSchema),
    }),

  createBackupSnapshot: (body: z.infer<typeof AdminBackupSnapshotRequestSchema>) =>
    client.request('/admin/backup/snapshot', {
      method: 'POST',
      body: JSON.stringify(AdminBackupSnapshotRequestSchema.parse(body)),
      schema: AdminBackupSnapshotSchema,
    }),

  restoreBackupHotswap: (body: z.infer<typeof AdminBackupRestoreRequestSchema>) =>
    client.request('/admin/backup/restore-hotswap', {
      method: 'POST',
      body: JSON.stringify(AdminBackupRestoreRequestSchema.parse(body)),
      schema: AdminBackupRestoreRunSchema,
    }),
});
