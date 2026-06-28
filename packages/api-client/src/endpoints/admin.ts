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
  AdminCategoryMappingsResponseSchema,
  AdminEmailEntrySchema,
  AdminEtlSummarySchema,
  AdminFeatureDetailSchema,
  AdminFeatureChangeRequestActionRequestSchema,
  AdminFeatureChangeRequestPagedResponseSchema,
  AdminFeatureChangeRequestRecordSchema,
  AdminFeatureOverridesResponseSchema,
  AdminFeaturePagedResponseSchema,
  AdminFeatureSourcesResponseSchema,
  AdminFeatureWeatherValuesResponseSchema,
  AdminFileStorageSettingsSchema,
  AdminFileStorageSettingsUpdateRequestSchema,
  AdminUserFileQuotaUpdateRequestSchema,
  AdminUserRoleMutationRequestSchema,
  AdminFeatureSortOrderSchema,
  AdminFeatureSortSchema,
  AdminFeatureRequestApproveSchema,
  AdminFeatureRequestPagedResponseSchema,
  AdminFeatureRequestRejectSchema,
  AdminFeatureRequestResultSchema,
  AdminMcpTokenIssueRequestSchema,
  AdminLocationAuditEntrySchema,
  AdminDayCopyRequestSchema,
  AdminDayDeleteRequestSchema,
  AdminDayMoveRequestSchema,
  AdminDedupDecisionRequestSchema,
  AdminDedupDecisionResponseSchema,
  AdminDedupReviewPagedResponseSchema,
  AdminDevSafetyActionResultSchema,
  AdminDsrCompleteRequestSchema,
  AdminDsrIdentityCheckRequestSchema,
  AdminDsrProcessRequestSchema,
  AdminDsrRejectRequestSchema,
  AdminDsrRequestListResponseSchema,
  AdminDsrRequestRecordSchema,
  AdminContentModerationActionRequestSchema,
  AdminContentReportListResponseSchema,
  AdminContentReportRecordSchema,
  AdminEmailDeliverabilitySchema,
  AdminOperationImpactSchema,
  AdminOperationResultSchema,
  AdminResetRunRequestSchema,
  AdminResetStatusResponseSchema,
  AdminRetentionDryRunRequestSchema,
  AdminRetentionExecuteRequestSchema,
  AdminRetentionRunListResponseSchema,
  AdminRetentionRunSchema,
  AdminRetentionSummarySchema,
  AdminSeedScenarioListResponseSchema,
  AdminSeedScenarioRunRequestSchema,
  AdminSecurityIncidentCloseRequestSchema,
  AdminSecurityIncidentCreateRequestSchema,
  AdminSecurityIncidentDecisionRequestSchema,
  AdminSecurityIncidentListResponseSchema,
  AdminSecurityIncidentNotifyRequestSchema,
  AdminSecurityIncidentRecordSchema,
  AdminSecurityIncidentReportRequestSchema,
  AdminSecurityIncidentTriageRequestSchema,
  AdminConsistencyReportsResponseSchema,
  AdminDebugLogStreamStatusSchema,
  AdminIntegrityIssueActionRequestSchema,
  AdminIntegrityIssueActionResponseSchema,
  AdminPagedResponseSchema,
  AdminPoiCopyRequestSchema,
  AdminPoiCreateRequestSchema,
  AdminPoiDeleteRequestSchema,
  AdminPoiDetailSchema,
  AdminPoiLinkStatusRequestSchema,
  AdminPoiMoveRequestSchema,
  AdminPoiPagedResponseSchema,
  AdminProviderImportJobCancelRequestSchema,
  AdminProviderImportJobRecordSchema,
  AdminProviderImportJobsResponseSchema,
  AdminProviderSyncResponseSchema,
  AdminRequestTimelineResponseSchema,
  AdminIntegrityIssuesResponseSchema,
  AdminPermissionMatrixResponseSchema,
  AdminStatsOverviewSchema,
  AdminSystemSummarySchema,
  AdminSystemDetailSchema,
  AdminTripCopyRequestSchema,
  AdminTripCreateRequestSchema,
  AdminTripDeleteRequestSchema,
  AdminTripDetailSchema,
  AdminTripMoveRequestSchema,
  AdminTripPagedResponseSchema,
  AdminTripStatusRequestSchema,
  AdminUserDetailSchema,
  AdminUpstreamApiCallLogsResponseSchema,
  AdminUpstreamSystemLogsResponseSchema,
  AvatarUploadUrlRequestSchema,
  DownloadUrlResponseSchema,
  McpTokenRevokeRequestSchema,
  McpTokenIssueResponseSchema,
  McpTokenSchema,
  UploadUrlResponseSchema,
  AttachmentLibraryPageSchema,
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

export interface AdminFeatureChangeRequestListParams {
  q?: string;
  status?: string[];
  action?: string[];
  pageSize?: number;
}

export interface AdminProviderSyncListParams {
  key?: string;
}

export interface AdminProviderImportJobListParams {
  status?: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  kind?: string;
  loadBatchId?: string;
  parentJobId?: string;
  pageSize?: number;
  cursor?: string;
}

export type AdminProviderImportJobCancelBody = z.infer<
  typeof AdminProviderImportJobCancelRequestSchema
>;

export interface AdminDedupReviewListParams {
  q?: string;
  status?: string[];
  provider?: string[];
  datasetKey?: string[];
  kind?: string[];
  category?: string[];
  minScore?: number;
  maxScore?: number;
  pageSize?: number;
  cursor?: string;
}

export interface AdminCategoryMappingListParams {
  q?: string;
  includeCounts?: boolean;
  activeOnly?: boolean;
}

export type AdminSeedScenarioRunBody = z.infer<typeof AdminSeedScenarioRunRequestSchema>;

export type AdminResetRunBody = z.infer<typeof AdminResetRunRequestSchema>;

export type AdminRetentionDryRunBody = z.infer<typeof AdminRetentionDryRunRequestSchema>;

export type AdminRetentionExecuteBody = z.infer<typeof AdminRetentionExecuteRequestSchema>;

export interface AdminSecurityIncidentListParams {
  status?: 'detected' | 'triage' | 'notification_decision' | 'reported' | 'closed';
  severity?: 'low' | 'medium' | 'high' | 'critical';
  overdue?: 'cpo_review' | 'external_report';
  pageSize?: number;
}

export type AdminSecurityIncidentCreateBody = z.infer<
  typeof AdminSecurityIncidentCreateRequestSchema
>;
export type AdminSecurityIncidentTriageBody = z.infer<
  typeof AdminSecurityIncidentTriageRequestSchema
>;
export type AdminSecurityIncidentDecisionBody = z.infer<
  typeof AdminSecurityIncidentDecisionRequestSchema
>;
export type AdminSecurityIncidentNotifyBody = z.infer<
  typeof AdminSecurityIncidentNotifyRequestSchema
>;
export type AdminSecurityIncidentReportBody = z.infer<
  typeof AdminSecurityIncidentReportRequestSchema
>;
export type AdminSecurityIncidentCloseBody = z.infer<
  typeof AdminSecurityIncidentCloseRequestSchema
>;

export interface AdminDsrRequestListParams {
  status?: 'received' | 'identity_check' | 'processing' | 'completed' | 'rejected' | 'withdrawn';
  requestType?: 'access' | 'correction' | 'delete' | 'suspend';
  overdue?: boolean;
  pageSize?: number;
}

export type AdminDsrIdentityCheckBody = z.infer<typeof AdminDsrIdentityCheckRequestSchema>;
export type AdminDsrProcessBody = z.infer<typeof AdminDsrProcessRequestSchema>;
export type AdminDsrCompleteBody = z.infer<typeof AdminDsrCompleteRequestSchema>;
export type AdminDsrRejectBody = z.infer<typeof AdminDsrRejectRequestSchema>;

export interface AdminContentReportListParams {
  status?:
    | 'received'
    | 'reviewing'
    | 'hidden'
    | 'taken_down'
    | 'rejected'
    | 'appealed'
    | 'restored';
  targetType?: 'trip' | 'comment' | 'attachment' | 'share_link';
  pageSize?: number;
}

export type AdminContentModerationActionBody = z.infer<
  typeof AdminContentModerationActionRequestSchema
>;

export interface AdminIntegrityIssueListParams {
  source?: 'all' | 'kor_travel_map' | 'pinvi_app';
  status?: 'open' | 'acknowledged' | 'resolved' | 'ignored';
  severity?: 'info' | 'warning' | 'error' | 'critical';
  violationType?: string;
  provider?: string;
  datasetKey?: string;
  featureId?: string;
  pageSize?: number;
  cursor?: string;
}

export interface AdminConsistencyReportListParams {
  severityMax?: 'OK' | 'WARN' | 'ERROR';
  pageSize?: number;
  cursor?: string;
}

export type AdminIntegrityIssueActionBody = z.infer<typeof AdminIntegrityIssueActionRequestSchema>;

export interface AdminSystemLogListParams {
  level?: 'debug' | 'info' | 'warning' | 'error' | 'critical';
  source?: string;
  q?: string;
  requestId?: string;
  pageSize?: number;
  cursor?: string;
}

export interface AdminUpstreamApiCallLogListParams {
  method?: string;
  minStatus?: number;
  path?: string;
  requestId?: string;
  pageSize?: number;
  cursor?: string;
}

export interface AdminFileListParams {
  page?: number;
  limit?: number;
  q?: string;
  scope?: 'trip' | 'day' | 'poi' | 'curated_plan' | 'curated_poi';
  userId?: string;
  tripId?: string;
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

  getSystemDetail: () =>
    client.request('/admin/system/detail', {
      method: 'GET',
      schema: AdminSystemDetailSchema,
    }),

  getEtlSummary: () =>
    client.request('/admin/etl/summary', {
      method: 'GET',
      schema: AdminEtlSummarySchema,
    }),

  listProviderSync: (params: AdminProviderSyncListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.key) qs.set('key', params.key);
    const path = `/admin/provider-sync${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminProviderSyncResponseSchema,
    });
  },

  listProviderImportJobs: (params: AdminProviderImportJobListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.kind) qs.set('kind', params.kind);
    if (params.loadBatchId) qs.set('load_batch_id', params.loadBatchId);
    if (params.parentJobId) qs.set('parent_job_id', params.parentJobId);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/provider-sync/import-jobs${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminProviderImportJobsResponseSchema,
    });
  },

  cancelProviderImportJob: (jobId: string, body: AdminProviderImportJobCancelBody) =>
    client.request(`/admin/provider-sync/import-jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify(body),
      schema: AdminProviderImportJobRecordSchema,
    }),

  listDedupReviews: (params: AdminDedupReviewListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    appendValues(qs, 'status', params.status);
    appendValues(qs, 'provider', params.provider);
    appendValues(qs, 'dataset_key', params.datasetKey);
    appendValues(qs, 'kind', params.kind);
    appendValues(qs, 'category', params.category);
    if (params.minScore !== undefined) qs.set('min_score', String(params.minScore));
    if (params.maxScore !== undefined) qs.set('max_score', String(params.maxScore));
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/dedup-review${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminDedupReviewPagedResponseSchema,
    });
  },

  decideDedupReview: (reviewId: string, body: z.infer<typeof AdminDedupDecisionRequestSchema>) =>
    client.request(`/admin/dedup-review/${encodeURIComponent(reviewId)}/verdict`, {
      method: 'POST',
      body: JSON.stringify(AdminDedupDecisionRequestSchema.parse(body)),
      schema: AdminDedupDecisionResponseSchema,
    }),

  listCategoryMappings: (params: AdminCategoryMappingListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.includeCounts !== undefined) qs.set('include_counts', String(params.includeCounts));
    if (params.activeOnly !== undefined) qs.set('active_only', String(params.activeOnly));
    const path = `/admin/category-mappings${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminCategoryMappingsResponseSchema,
    });
  },

  listSeedScenarios: () =>
    client.request('/admin/seed/scenarios', {
      method: 'GET',
      schema: AdminSeedScenarioListResponseSchema,
    }),

  runSeedScenario: (scenarioKey: string, body: AdminSeedScenarioRunBody) =>
    client.request(`/admin/seed/scenarios/${encodeURIComponent(scenarioKey)}`, {
      method: 'POST',
      body: JSON.stringify(AdminSeedScenarioRunRequestSchema.parse(body)),
      schema: AdminDevSafetyActionResultSchema,
    }),

  getResetStatus: () =>
    client.request('/admin/reset/status', {
      method: 'GET',
      schema: AdminResetStatusResponseSchema,
    }),

  runReset: (body: AdminResetRunBody) =>
    client.request('/admin/reset', {
      method: 'POST',
      body: JSON.stringify(AdminResetRunRequestSchema.parse(body)),
      schema: AdminDevSafetyActionResultSchema,
    }),

  getRetentionSummary: () =>
    client.request('/admin/retention/summary', {
      method: 'GET',
      schema: AdminRetentionSummarySchema,
    }),

  listRetentionRuns: (pageSize = 20) => {
    const qs = new URLSearchParams();
    qs.set('page_size', String(pageSize));
    return client.request(`/admin/retention/runs?${qs.toString()}`, {
      method: 'GET',
      schema: AdminRetentionRunListResponseSchema,
    });
  },

  createRetentionDryRun: (body: AdminRetentionDryRunBody) =>
    client.request('/admin/retention/dry-run', {
      method: 'POST',
      body: JSON.stringify(AdminRetentionDryRunRequestSchema.parse(body)),
      schema: AdminRetentionRunSchema,
    }),

  executeRetention: (body: AdminRetentionExecuteBody) =>
    client.request('/admin/retention/execute', {
      method: 'POST',
      body: JSON.stringify(AdminRetentionExecuteRequestSchema.parse(body)),
      schema: AdminRetentionRunSchema,
    }),

  listSecurityIncidents: (params: AdminSecurityIncidentListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.severity) qs.set('severity', params.severity);
    if (params.overdue) qs.set('overdue', params.overdue);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    const path = `/admin/incidents${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminSecurityIncidentListResponseSchema,
    });
  },

  createSecurityIncident: (body: AdminSecurityIncidentCreateBody) =>
    client.request('/admin/incidents', {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentCreateRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  triageSecurityIncident: (incidentId: string, body: AdminSecurityIncidentTriageBody) =>
    client.request(`/admin/incidents/${encodeURIComponent(incidentId)}/triage`, {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentTriageRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  decideSecurityIncidentNotification: (
    incidentId: string,
    body: AdminSecurityIncidentDecisionBody,
  ) =>
    client.request(`/admin/incidents/${encodeURIComponent(incidentId)}/notification-decision`, {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentDecisionRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  notifySecurityIncidentSubjects: (incidentId: string, body: AdminSecurityIncidentNotifyBody) =>
    client.request(`/admin/incidents/${encodeURIComponent(incidentId)}/notify`, {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentNotifyRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  reportSecurityIncidentExternal: (incidentId: string, body: AdminSecurityIncidentReportBody) =>
    client.request(`/admin/incidents/${encodeURIComponent(incidentId)}/report`, {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentReportRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  closeSecurityIncident: (incidentId: string, body: AdminSecurityIncidentCloseBody) =>
    client.request(`/admin/incidents/${encodeURIComponent(incidentId)}/close`, {
      method: 'POST',
      body: JSON.stringify(AdminSecurityIncidentCloseRequestSchema.parse(body)),
      schema: AdminSecurityIncidentRecordSchema,
    }),

  listDsrRequests: (params: AdminDsrRequestListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.requestType) qs.set('request_type', params.requestType);
    if (params.overdue !== undefined) qs.set('overdue', String(params.overdue));
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    const path = `/admin/dsr${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminDsrRequestListResponseSchema,
    });
  },

  identityCheckDsrRequest: (requestId: string, body: AdminDsrIdentityCheckBody) =>
    client.request(`/admin/dsr/${encodeURIComponent(requestId)}/identity-check`, {
      method: 'POST',
      body: JSON.stringify(AdminDsrIdentityCheckRequestSchema.parse(body)),
      schema: AdminDsrRequestRecordSchema,
    }),

  processDsrRequest: (requestId: string, body: AdminDsrProcessBody) =>
    client.request(`/admin/dsr/${encodeURIComponent(requestId)}/process`, {
      method: 'POST',
      body: JSON.stringify(AdminDsrProcessRequestSchema.parse(body)),
      schema: AdminDsrRequestRecordSchema,
    }),

  completeDsrRequest: (requestId: string, body: AdminDsrCompleteBody) =>
    client.request(`/admin/dsr/${encodeURIComponent(requestId)}/complete`, {
      method: 'POST',
      body: JSON.stringify(AdminDsrCompleteRequestSchema.parse(body)),
      schema: AdminDsrRequestRecordSchema,
    }),

  rejectDsrRequest: (requestId: string, body: AdminDsrRejectBody) =>
    client.request(`/admin/dsr/${encodeURIComponent(requestId)}/reject`, {
      method: 'POST',
      body: JSON.stringify(AdminDsrRejectRequestSchema.parse(body)),
      schema: AdminDsrRequestRecordSchema,
    }),

  listContentReports: (params: AdminContentReportListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.targetType) qs.set('target_type', params.targetType);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    const path = `/admin/moderation/reports${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminContentReportListResponseSchema,
    });
  },

  reviewContentReport: (reportId: string, body: AdminContentModerationActionBody) =>
    client.request(`/admin/moderation/reports/${encodeURIComponent(reportId)}/review`, {
      method: 'POST',
      body: JSON.stringify(AdminContentModerationActionRequestSchema.parse(body)),
      schema: AdminContentReportRecordSchema,
    }),

  hideContentReport: (reportId: string, body: AdminContentModerationActionBody) =>
    client.request(`/admin/moderation/reports/${encodeURIComponent(reportId)}/hide`, {
      method: 'POST',
      body: JSON.stringify(AdminContentModerationActionRequestSchema.parse(body)),
      schema: AdminContentReportRecordSchema,
    }),

  takedownContentReport: (reportId: string, body: AdminContentModerationActionBody) =>
    client.request(`/admin/moderation/reports/${encodeURIComponent(reportId)}/takedown`, {
      method: 'POST',
      body: JSON.stringify(AdminContentModerationActionRequestSchema.parse(body)),
      schema: AdminContentReportRecordSchema,
    }),

  restoreContentReport: (reportId: string, body: AdminContentModerationActionBody) =>
    client.request(`/admin/moderation/reports/${encodeURIComponent(reportId)}/restore`, {
      method: 'POST',
      body: JSON.stringify(AdminContentModerationActionRequestSchema.parse(body)),
      schema: AdminContentReportRecordSchema,
    }),

  rejectContentReport: (reportId: string, body: AdminContentModerationActionBody) =>
    client.request(`/admin/moderation/reports/${encodeURIComponent(reportId)}/reject`, {
      method: 'POST',
      body: JSON.stringify(AdminContentModerationActionRequestSchema.parse(body)),
      schema: AdminContentReportRecordSchema,
    }),

  listIntegrityIssues: (params: AdminIntegrityIssueListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.source) qs.set('source', params.source);
    if (params.status) qs.set('status', params.status);
    if (params.severity) qs.set('severity', params.severity);
    if (params.violationType) qs.set('violation_type', params.violationType);
    if (params.provider) qs.set('provider', params.provider);
    if (params.datasetKey) qs.set('dataset_key', params.datasetKey);
    if (params.featureId) qs.set('feature_id', params.featureId);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/integrity/issues${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminIntegrityIssuesResponseSchema,
    });
  },

  actionIntegrityIssue: (issueId: string, body: AdminIntegrityIssueActionBody) =>
    client.request(`/admin/integrity/issues/${encodeURIComponent(issueId)}/action`, {
      method: 'POST',
      body: JSON.stringify(AdminIntegrityIssueActionRequestSchema.parse(body)),
      schema: AdminIntegrityIssueActionResponseSchema,
    }),

  listConsistencyReports: (params: AdminConsistencyReportListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.severityMax) qs.set('severity_max', params.severityMax);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/integrity/reports${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminConsistencyReportsResponseSchema,
    });
  },

  listUpstreamSystemLogs: (params: AdminSystemLogListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.level) qs.set('level', params.level);
    if (params.source) qs.set('source', params.source);
    if (params.q) qs.set('q', params.q);
    if (params.requestId) qs.set('request_id', params.requestId);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/debug/logs/system${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminUpstreamSystemLogsResponseSchema,
    });
  },

  listUpstreamApiCallLogs: (params: AdminUpstreamApiCallLogListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.method) qs.set('method', params.method);
    if (params.minStatus !== undefined) qs.set('min_status', String(params.minStatus));
    if (params.path) qs.set('path', params.path);
    if (params.requestId) qs.set('request_id', params.requestId);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    if (params.cursor) qs.set('cursor', params.cursor);
    const path = `/admin/debug/logs/api-calls${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminUpstreamApiCallLogsResponseSchema,
    });
  },

  getDebugLogStreamStatus: () =>
    client.request('/admin/debug/logs/stream/status', {
      method: 'GET',
      schema: AdminDebugLogStreamStatusSchema,
    }),

  getRequestTimeline: (requestId: string) =>
    client.request(`/admin/debug/request/${encodeURIComponent(requestId)}`, {
      method: 'GET',
      schema: AdminRequestTimelineResponseSchema,
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

  getFileSettings: () =>
    client.request('/admin/settings/files', {
      method: 'GET',
      schema: AdminFileStorageSettingsSchema,
    }),

  updateFileSettings: (body: z.infer<typeof AdminFileStorageSettingsUpdateRequestSchema>) =>
    client.request('/admin/settings/files', {
      method: 'PUT',
      body: JSON.stringify(AdminFileStorageSettingsUpdateRequestSchema.parse(body)),
      schema: AdminFileStorageSettingsSchema,
    }),

  listFiles: (params: AdminFileListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.q) qs.set('q', params.q);
    if (params.scope) qs.set('scope', params.scope);
    if (params.userId) qs.set('user_id', params.userId);
    if (params.tripId) qs.set('trip_id', params.tripId);
    return client.request(`/admin/files${qs.toString() ? `?${qs.toString()}` : ''}`, {
      method: 'GET',
      schema: AttachmentLibraryPageSchema,
    });
  },

  fileDownloadUrl: (attachmentId: string) =>
    client.request(`/admin/files/${attachmentId}/download-url`, {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  deleteFile: (attachmentId: string, body: z.infer<typeof AdminActionRequestSchema>) =>
    client.requestNoContent(`/admin/files/${attachmentId}`, {
      method: 'DELETE',
      body: JSON.stringify(AdminActionRequestSchema.parse(body)),
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

  getFeatureSources: (featureId: string) =>
    client.request(`/admin/features/${encodeURIComponent(featureId)}/sources`, {
      method: 'GET',
      schema: AdminFeatureSourcesResponseSchema,
    }),

  getFeatureOverrides: (featureId: string) =>
    client.request(`/admin/features/${encodeURIComponent(featureId)}/overrides`, {
      method: 'GET',
      schema: AdminFeatureOverridesResponseSchema,
    }),

  getFeatureWeatherValues: (featureId: string) =>
    client.request(`/admin/features/${encodeURIComponent(featureId)}/weather-values`, {
      method: 'GET',
      schema: AdminFeatureWeatherValuesResponseSchema,
    }),

  /** kor-travel-map admin change request 큐 proxy (T-210). */
  listFeatureChangeRequests: (params: AdminFeatureChangeRequestListParams = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    appendValues(qs, 'status', params.status);
    appendValues(qs, 'action', params.action);
    if (params.pageSize) qs.set('page_size', String(params.pageSize));
    const path = `/admin/features/change-requests${qs.toString() ? `?${qs.toString()}` : ''}`;
    return client.request(path, {
      method: 'GET',
      schema: AdminFeatureChangeRequestPagedResponseSchema,
    });
  },

  approveFeatureChangeRequest: (
    requestId: string,
    body: z.infer<typeof AdminFeatureChangeRequestActionRequestSchema>,
  ) =>
    client.request(`/admin/features/change-requests/${encodeURIComponent(requestId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(AdminFeatureChangeRequestActionRequestSchema.parse(body)),
      schema: AdminFeatureChangeRequestRecordSchema,
    }),

  rejectFeatureChangeRequest: (
    requestId: string,
    body: z.infer<typeof AdminFeatureChangeRequestActionRequestSchema>,
  ) =>
    client.request(`/admin/features/change-requests/${encodeURIComponent(requestId)}/reject`, {
      method: 'POST',
      body: JSON.stringify(AdminFeatureChangeRequestActionRequestSchema.parse(body)),
      schema: AdminFeatureChangeRequestRecordSchema,
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

  getRbacPermissionMatrix: () =>
    client.request('/admin/rbac/permission-matrix', {
      method: 'GET',
      schema: AdminPermissionMatrixResponseSchema,
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

  grantUserRole: (userId: string, body: z.infer<typeof AdminUserRoleMutationRequestSchema>) =>
    client.request(`/admin/users/${userId}/roles/grant`, {
      method: 'POST',
      body: JSON.stringify(AdminUserRoleMutationRequestSchema.parse(body)),
      schema: AdminUserDetailSchema,
    }),

  revokeUserRole: (userId: string, body: z.infer<typeof AdminUserRoleMutationRequestSchema>) =>
    client.request(`/admin/users/${userId}/roles/revoke`, {
      method: 'POST',
      body: JSON.stringify(AdminUserRoleMutationRequestSchema.parse(body)),
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

  updateUserFileQuota: (
    userId: string,
    body: z.infer<typeof AdminUserFileQuotaUpdateRequestSchema>,
  ) =>
    client.request(`/admin/users/${userId}/file-quota`, {
      method: 'PUT',
      body: JSON.stringify(AdminUserFileQuotaUpdateRequestSchema.parse(body)),
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

  getTripOperationImpact: (tripId: string) =>
    client.request(`/admin/trips/${tripId}/operation-impact`, {
      method: 'GET',
      schema: AdminOperationImpactSchema,
    }),

  copyTrip: (tripId: string, body: z.infer<typeof AdminTripCopyRequestSchema>) =>
    client.request(`/admin/trips/${tripId}/copy`, {
      method: 'POST',
      body: JSON.stringify(AdminTripCopyRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  moveTrip: (tripId: string, body: z.infer<typeof AdminTripMoveRequestSchema>) =>
    client.request(`/admin/trips/${tripId}/move`, {
      method: 'POST',
      body: JSON.stringify(AdminTripMoveRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  deleteTrip: (tripId: string, body: z.infer<typeof AdminTripDeleteRequestSchema>) =>
    client.request(`/admin/trips/${tripId}`, {
      method: 'DELETE',
      body: JSON.stringify(AdminTripDeleteRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  getDayOperationImpact: (tripId: string, dayIndex: number) =>
    client.request(`/admin/trips/${tripId}/days/${dayIndex}/operation-impact`, {
      method: 'GET',
      schema: AdminOperationImpactSchema,
    }),

  copyTripDay: (
    tripId: string,
    dayIndex: number,
    body: z.infer<typeof AdminDayCopyRequestSchema>,
  ) =>
    client.request(`/admin/trips/${tripId}/days/${dayIndex}/copy`, {
      method: 'POST',
      body: JSON.stringify(AdminDayCopyRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  moveTripDay: (
    tripId: string,
    dayIndex: number,
    body: z.infer<typeof AdminDayMoveRequestSchema>,
  ) =>
    client.request(`/admin/trips/${tripId}/days/${dayIndex}/move`, {
      method: 'POST',
      body: JSON.stringify(AdminDayMoveRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  deleteTripDay: (
    tripId: string,
    dayIndex: number,
    body: z.infer<typeof AdminDayDeleteRequestSchema>,
  ) =>
    client.request(`/admin/trips/${tripId}/days/${dayIndex}`, {
      method: 'DELETE',
      body: JSON.stringify(AdminDayDeleteRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
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

  getPoiOperationImpact: (poiId: string) =>
    client.request(`/admin/pois/${poiId}/operation-impact`, {
      method: 'GET',
      schema: AdminOperationImpactSchema,
    }),

  copyPoi: (poiId: string, body: z.infer<typeof AdminPoiCopyRequestSchema>) =>
    client.request(`/admin/pois/${poiId}/copy`, {
      method: 'POST',
      body: JSON.stringify(AdminPoiCopyRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  movePoi: (poiId: string, body: z.infer<typeof AdminPoiMoveRequestSchema>) =>
    client.request(`/admin/pois/${poiId}/move`, {
      method: 'POST',
      body: JSON.stringify(AdminPoiMoveRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
    }),

  deletePoi: (poiId: string, body: z.infer<typeof AdminPoiDeleteRequestSchema>) =>
    client.request(`/admin/pois/${poiId}`, {
      method: 'DELETE',
      body: JSON.stringify(AdminPoiDeleteRequestSchema.parse(body)),
      schema: AdminOperationResultSchema,
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

  getEmailDeliverability: () =>
    client.request('/admin/emails/deliverability', {
      method: 'GET',
      schema: AdminEmailDeliverabilitySchema,
    }),

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
