import {
  AdminActionRequestSchema,
  AdminAuditEntrySchema,
  AdminBackupSnapshotRequestSchema,
  AdminBackupSnapshotSchema,
  AdminChainVerifySchema,
  AdminEmailEntrySchema,
  AdminPagedResponseSchema,
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

  getUser: (
    userId: string,
    params: { reveal?: boolean; accessReason?: string } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.reveal) qs.set('reveal', 'true');
    if (params.accessReason) qs.set('access_reason', params.accessReason);
    const path = `/admin/users/${userId}${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminUserDetailSchema,
    });
  },

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
});
