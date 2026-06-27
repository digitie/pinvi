import {
  AdminActionRequestSchema,
  AdminAvatarApplyRequestSchema,
  AdminAvatarDeleteRequestSchema,
  AdminAvatarSettingsSchema,
  AdminAvatarSettingsUpdateRequestSchema,
  AdminApiCallEntrySchema,
  AdminAuditEntrySchema,
  AdminBackupRestoreRequestSchema,
  AdminBackupRestoreRunSchema,
  AdminBackupSnapshotRequestSchema,
  AdminBackupSnapshotSchema,
  AdminChainVerifySchema,
  AdminEmailEntrySchema,
  AdminFeatureDetailSchema,
  AdminFeaturePagedResponseSchema,
  AdminFeatureSortOrderSchema,
  AdminFeatureSortSchema,
  AdminFeatureRequestApproveSchema,
  AdminFeatureRequestPagedResponseSchema,
  AdminFeatureRequestRejectSchema,
  AdminFeatureRequestResultSchema,
  AdminMcpTokenIssueRequestSchema,
  AdminLocationAuditEntrySchema,
  AdminPagedResponseSchema,
  AdminPoiCreateRequestSchema,
  AdminPoiDetailSchema,
  AdminPoiLinkStatusRequestSchema,
  AdminPoiPagedResponseSchema,
  AdminStatsOverviewSchema,
  AdminSystemSummarySchema,
  AdminTripCreateRequestSchema,
  AdminTripDetailSchema,
  AdminTripPagedResponseSchema,
  AdminTripStatusRequestSchema,
  AdminUserDetailSchema,
  AvatarUploadUrlRequestSchema,
  DownloadUrlResponseSchema,
  McpTokenRevokeRequestSchema,
  McpTokenIssueResponseSchema,
  McpTokenSchema,
  UploadUrlResponseSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

export interface AdminFeatureListParams {
  q?: string;
  kind?: string[];
  category?: string[];
  status?: string[];
  provider?: string[];
  datasetKey?: string[];
  hasCoord?: boolean;
  hasIssue?: boolean;
  issueType?: string[];
  updatedFrom?: string;
  updatedTo?: string;
  pageSize?: number;
  cursor?: string;
  sort?: z.infer<typeof AdminFeatureSortSchema>;
  order?: z.infer<typeof AdminFeatureSortOrderSchema>;
}

function appendValues(qs: URLSearchParams, key: string, values: string[] | undefined) {
  for (const value of values ?? []) {
    if (value) qs.append(key, value);
  }
}

/** `docs/api/admin.md` Sprint 3 범위. */
export const adminApi = (client: ApiClient) => ({
  getStatsOverview: () =>
    client.request('/admin/stats/overview', {
      method: 'GET',
      schema: AdminStatsOverviewSchema,
    }),

  getSystemSummary: () =>
    client.request('/admin/system/summary', {
      method: 'GET',
      schema: AdminSystemSummarySchema,
    }),

  getAvatarSettings: () =>
    client.request('/admin/settings/avatar', {
      method: 'GET',
      schema: AdminAvatarSettingsSchema,
    }),

  updateAvatarSettings: (body: z.infer<typeof AdminAvatarSettingsUpdateRequestSchema>) =>
    client.request('/admin/settings/avatar', {
      method: 'PUT',
      body: JSON.stringify(AdminAvatarSettingsUpdateRequestSchema.parse(body)),
      schema: AdminAvatarSettingsSchema,
    }),

  /** kor-travel-map admin feature 목록 proxy (T-209, read-only). */
  listFeatures: (params: AdminFeatureListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    appendValues(qs, 'kind', params.kind);
    appendValues(qs, 'category', params.category);
    appendValues(qs, 'status', params.status);
    appendValues(qs, 'provider', params.provider);
    appendValues(qs, 'dataset_key', params.datasetKey);
    appendValues(qs, 'issue_type', params.issueType);
    if (params.hasCoord !== undefined) qs.set('has_coord', String(params.hasCoord));
    if (params.hasIssue !== undefined) qs.set('has_issue', String(params.hasIssue));
    if (params.updatedFrom) qs.set('updated_from', params.updatedFrom);
    if (params.updatedTo) qs.set('updated_to', params.updatedTo);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    if (params.sort) qs.set('sort', params.sort);
    if (params.order) qs.set('order', params.order);
    const path = `/admin/features${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminFeaturePagedResponseSchema,
    });
  },

  getFeature: (featureId: string) =>
    client.request(`/admin/features/${encodeURIComponent(featureId)}`, {
      method: 'GET',
      schema: AdminFeatureDetailSchema,
    }),

  /** 사용자 feature 제안 검토 큐 (T-179). */
  listFeatureRequests: (params: { status?: string; page?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    const path = `/admin/feature-requests${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminFeatureRequestPagedResponseSchema,
    });
  },

  approveFeatureRequest: (
    requestId: string,
    body: z.infer<typeof AdminFeatureRequestApproveSchema>,
  ) =>
    client.request(`/admin/feature-requests/${requestId}/approve`, {
      method: 'POST',
      body: JSON.stringify(AdminFeatureRequestApproveSchema.parse(body)),
      schema: AdminFeatureRequestResultSchema,
    }),

  rejectFeatureRequest: (
    requestId: string,
    body: z.infer<typeof AdminFeatureRequestRejectSchema>,
  ) =>
    client.request(`/admin/feature-requests/${requestId}/reject`, {
      method: 'POST',
      body: JSON.stringify(AdminFeatureRequestRejectSchema.parse(body)),
      schema: AdminFeatureRequestResultSchema,
    }),

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

  createUserAvatarUploadUrl: (userId: string, body: z.infer<typeof AvatarUploadUrlRequestSchema>) =>
    client.request(`/admin/users/${userId}/avatar/upload-url`, {
      method: 'POST',
      body: JSON.stringify(AvatarUploadUrlRequestSchema.parse(body)),
      schema: UploadUrlResponseSchema,
    }),

  updateUserAvatar: (userId: string, body: z.infer<typeof AdminAvatarApplyRequestSchema>) =>
    client.request(`/admin/users/${userId}/avatar`, {
      method: 'PUT',
      body: JSON.stringify(AdminAvatarApplyRequestSchema.parse(body)),
      schema: AdminUserDetailSchema,
    }),

  getUserAvatarDownloadUrl: (userId: string) =>
    client.request(`/admin/users/${userId}/avatar/download-url`, {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  deleteUserAvatar: (userId: string, body: z.infer<typeof AdminAvatarDeleteRequestSchema>) =>
    client.request(`/admin/users/${userId}/avatar`, {
      method: 'DELETE',
      body: JSON.stringify(AdminAvatarDeleteRequestSchema.parse(body)),
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

  createTrip: (body: z.infer<typeof AdminTripCreateRequestSchema>) =>
    client.request('/admin/trips', {
      method: 'POST',
      body: JSON.stringify(AdminTripCreateRequestSchema.parse(body)),
      schema: AdminTripDetailSchema,
    }),

  updateTripStatus: (tripId: string, body: z.infer<typeof AdminTripStatusRequestSchema>) =>
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

  createPoi: (body: z.infer<typeof AdminPoiCreateRequestSchema>) =>
    client.request('/admin/pois', {
      method: 'POST',
      body: JSON.stringify(AdminPoiCreateRequestSchema.parse(body)),
      schema: AdminPoiDetailSchema,
    }),

  updatePoiLinkStatus: (poiId: string, body: z.infer<typeof AdminPoiLinkStatusRequestSchema>) =>
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

  listLocationAudit: (
    params: {
      userId?: string;
      from?: string;
      to?: string;
      limit?: number;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.userId) qs.set('user_id', params.userId);
    if (params.from) qs.set('from', params.from);
    if (params.to) qs.set('to', params.to);
    if (params.limit) qs.set('limit', String(params.limit));
    const path = `/admin/audit/location${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: z.array(AdminLocationAuditEntrySchema),
    });
  },

  listApiCalls: (
    params: {
      provider?: string;
      statusCode?: number;
      errorClass?: string;
      limit?: number;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.provider) qs.set('provider', params.provider);
    if (params.statusCode !== undefined) qs.set('status_code', String(params.statusCode));
    if (params.errorClass) qs.set('error_class', params.errorClass);
    if (params.limit) qs.set('limit', String(params.limit));
    const path = `/admin/api-calls${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: z.array(AdminApiCallEntrySchema),
    });
  },

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

  listMcpTokens: (
    params: {
      userId?: string;
      status?: 'active' | 'expired' | 'revoked';
      q?: string;
      limit?: number;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.userId) qs.set('user_id', params.userId);
    if (params.status) qs.set('status', params.status);
    if (params.q) qs.set('q', params.q);
    if (params.limit) qs.set('limit', String(params.limit));
    const path = `/admin/mcp-tokens${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: z.array(McpTokenSchema),
    });
  },

  issueMcpToken: (body: z.input<typeof AdminMcpTokenIssueRequestSchema>) =>
    client.request('/admin/mcp-tokens', {
      method: 'POST',
      body: JSON.stringify(AdminMcpTokenIssueRequestSchema.parse(body)),
      schema: McpTokenIssueResponseSchema,
    }),

  revokeMcpToken: (tokenId: string, body: z.infer<typeof McpTokenRevokeRequestSchema>) =>
    client.request(`/admin/mcp-tokens/${tokenId}/revoke`, {
      method: 'POST',
      body: JSON.stringify(McpTokenRevokeRequestSchema.parse(body)),
      schema: McpTokenSchema,
    }),
});
