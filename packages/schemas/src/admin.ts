import { z } from 'zod';
import { Iso8601Schema, NonNegativeDecimalStringSchema } from './common';
import { AttachmentLibraryItemSchema, AvatarApplyRequestSchema } from './storage';
import { TripPrimaryRegionSourceSchema, TripStatusSchema, TripVisibilitySchema } from './trip';

/** `docs/api/admin.md` §6.4 — 목록 응답은 PII 마스킹. */
export const AdminUserSummarySchema = z.object({
  user_id: z.string().uuid(),
  email_masked: z.string(),
  nickname: z.string().nullable(),
  status: z.enum(['pending_verification', 'pending_profile', 'active', 'disabled', 'deleted']),
  roles: z.array(z.enum(['user', 'admin', 'operator', 'cpo'])),
  email_verified_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
});
export type AdminUserSummary = z.infer<typeof AdminUserSummarySchema>;

/** admin_audit_log 항목 — chain hash + occurred_at. */
export const AdminAuditEntrySchema = z.object({
  log_id: z.number().int(),
  actor_user_id: z.string().uuid(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string().nullable(),
  access_reason: z.string().nullable(),
  target_pii_fields: z.array(z.string()).nullable(),
  prev_hash: z.string(),
  content_hash: z.string(),
  occurred_at: Iso8601Schema,
});
export type AdminAuditEntry = z.infer<typeof AdminAuditEntrySchema>;

/** location_access_log CPO 조회 — 좌표는 4자리 mask. */
export const AdminLocationAuditEntrySchema = z.object({
  log_id: z.number().int(),
  user_id: z.string().uuid(),
  occurred_at: Iso8601Schema,
  endpoint: z.string(),
  purpose: z.string(),
  lat_masked: z.string().nullable(),
  lng_masked: z.string().nullable(),
  request_id: z.string().uuid(),
  ip_hash: z.string(),
  prev_hash: z.string(),
  content_hash: z.string(),
});
export type AdminLocationAuditEntry = z.infer<typeof AdminLocationAuditEntrySchema>;

/** app.api_call_log read-only 행. */
export const AdminApiCallEntrySchema = z.object({
  log_id: z.number().int(),
  provider: z.string(),
  endpoint: z.string(),
  status_code: z.number().int().nullable(),
  latency_ms: z.number().int().nullable(),
  error_class: z.string().nullable(),
  error_message: z.string().nullable(),
  request_id: z.string().uuid().nullable(),
  occurred_at: Iso8601Schema,
});
export type AdminApiCallEntry = z.infer<typeof AdminApiCallEntrySchema>;

/** `/admin/stats/overview` — Pinvi app-owned 지표. */
export const AdminStatsOverviewSchema = z.object({
  users_total: z.number().int(),
  users_24h: z.number().int(),
  users_pending_verification: z.number().int(),
  trips_total: z.number().int(),
  trips_active: z.number().int(),
  pois_total: z.number().int(),
  email_queue_pending: z.number().int(),
  api_calls_24h: z.number().int(),
  api_calls_failed_24h: z.number().int(),
  features_by_kind: z.record(z.string(), z.number().int()).default({}),
  etl_last_24h: z
    .object({
      success: z.number().int(),
      failed: z.number().int(),
    })
    .default({ success: 0, failed: 0 }),
});
export type AdminStatsOverview = z.infer<typeof AdminStatsOverviewSchema>;

export const AdminSystemStatusSchema = z.enum(['ok', 'degraded', 'down', 'unknown']);
export type AdminSystemStatus = z.infer<typeof AdminSystemStatusSchema>;

export const AdminSystemServiceStatusSchema = z.object({
  key: z.string(),
  label: z.string(),
  status: AdminSystemStatusSchema,
  message: z.string().nullable().default(null),
  latency_ms: z.number().int().nullable().default(null),
});
export type AdminSystemServiceStatus = z.infer<typeof AdminSystemServiceStatusSchema>;

export const AdminSystemSummarySchema = z.object({
  generated_at: Iso8601Schema,
  services: z.array(AdminSystemServiceStatusSchema),
});
export type AdminSystemSummary = z.infer<typeof AdminSystemSummarySchema>;

export const AdminFeatureSortSchema = z.enum([
  'name',
  'updated_at',
  'created_at',
  'kind',
  'status',
  'provider',
  'issue_count',
]);
export type AdminFeatureSort = z.infer<typeof AdminFeatureSortSchema>;

export const AdminFeatureSortOrderSchema = z.enum(['asc', 'desc']);
export type AdminFeatureSortOrder = z.infer<typeof AdminFeatureSortOrderSchema>;

const AdminFeatureJsonObjectSchema = z.record(z.string(), z.unknown());

export const AdminFeatureIssueSummarySchema = z.object({
  issue_id: z.string().nullable().default(null),
  violation_type: z.string().nullable().default(null),
  severity: z.string().nullable().default(null),
  message: z.string().nullable().default(null),
  detected_at: Iso8601Schema.nullable().default(null),
});
export type AdminFeatureIssueSummary = z.infer<typeof AdminFeatureIssueSummarySchema>;

export const AdminFeatureSummarySchema = z.object({
  feature_id: z.string(),
  kind: z.string(),
  name: z.string(),
  category: z.string(),
  status: z.string(),
  lon: z.number().nullable().default(null),
  lat: z.number().nullable().default(null),
  address_label: z.string().nullable().default(null),
  primary_provider: z.string().nullable().default(null),
  primary_dataset_key: z.string().nullable().default(null),
  issue_count: z.number().int().default(0),
  issues: z.array(AdminFeatureIssueSummarySchema).default([]),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminFeatureSummary = z.infer<typeof AdminFeatureSummarySchema>;

export const AdminFeaturePagedResponseSchema = z.object({
  items: z.array(AdminFeatureSummarySchema),
  page_size: z.number().int(),
  next_cursor: z.string().nullable().default(null),
  duration_ms: z.number().int().nullable().default(null),
});
export type AdminFeaturePagedResponse = z.infer<typeof AdminFeaturePagedResponseSchema>;

export const AdminFeatureChangeRequestRecordSchema = z.object({
  request_id: z.string(),
  feature_id: z.string(),
  action: z.string(),
  status: z.string(),
  review_mode: z.string(),
  payload: AdminFeatureJsonObjectSchema.default({}),
  reason: z.string().nullable().default(null),
  requested_by: z.string().nullable().default(null),
  reviewed_by: z.string().nullable().default(null),
  reviewed_at: Iso8601Schema.nullable().default(null),
  applied_at: Iso8601Schema.nullable().default(null),
  created_at: Iso8601Schema,
});
export type AdminFeatureChangeRequestRecord = z.infer<typeof AdminFeatureChangeRequestRecordSchema>;

export const AdminFeatureDetailFeatureSchema = z.object({
  feature_id: z.string(),
  kind: z.string(),
  name: z.string(),
  category: z.string(),
  status: z.string(),
  lon: z.number().nullable().default(null),
  lat: z.number().nullable().default(null),
  coord_precision_digits: z.number().int().nullable().default(null),
  area_square_meters: z.number().nullable().default(null),
  address: AdminFeatureJsonObjectSchema.default({}),
  detail: AdminFeatureJsonObjectSchema.default({}),
  urls: AdminFeatureJsonObjectSchema.default({}),
  raw_refs: z.array(AdminFeatureJsonObjectSchema).default([]),
  legal_dong_code: z.string().nullable().default(null),
  road_name_code: z.string().nullable().default(null),
  road_address_management_no: z.string().nullable().default(null),
  admin_dong_code: z.string().nullable().default(null),
  sido_code: z.string().nullable().default(null),
  sigungu_code: z.string().nullable().default(null),
  marker_icon: z.string().nullable().default(null),
  marker_color: z.string().nullable().default(null),
  parent_feature_id: z.string().nullable().default(null),
  sibling_group_id: z.string().nullable().default(null),
  data_origin: z.string().nullable().default(null),
  data_version: z.number().int().nullable().default(null),
  user_change_kind: z.string().nullable().default(null),
  user_change_status: z.string().nullable().default(null),
  user_change_request_id: z.string().nullable().default(null),
  user_deleted_at: Iso8601Schema.nullable().default(null),
  user_deleted_by: z.string().nullable().default(null),
  user_change_reason: z.string().nullable().default(null),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
  deleted_at: Iso8601Schema.nullable().default(null),
});
export type AdminFeatureDetailFeature = z.infer<typeof AdminFeatureDetailFeatureSchema>;

export const AdminFeatureDetailSourceSchema = z.object({
  source_record_key: z.string(),
  provider: z.string(),
  dataset_key: z.string(),
  source_entity_type: z.string(),
  source_entity_id: z.string(),
  source_version: z.string().nullable().default(null),
  source_role: z.string(),
  match_method: z.string(),
  confidence: z.number().int(),
  is_primary_source: z.boolean(),
  raw_name: z.string().nullable().default(null),
  raw_address: z.string().nullable().default(null),
  raw_longitude: z.number().nullable().default(null),
  raw_latitude: z.number().nullable().default(null),
  raw_payload_hash: z.string().nullable().default(null),
  raw_data: AdminFeatureJsonObjectSchema.default({}),
  fetched_at: Iso8601Schema,
  imported_at: Iso8601Schema,
  expires_at: Iso8601Schema.nullable().default(null),
  linked_at: Iso8601Schema,
});
export type AdminFeatureDetailSource = z.infer<typeof AdminFeatureDetailSourceSchema>;

export const AdminFeatureDetailIssueSchema = z.object({
  issue_id: z.string(),
  provider: z.string().nullable().default(null),
  dataset_key: z.string().nullable().default(null),
  source_record_key: z.string().nullable().default(null),
  violation_type: z.string(),
  severity: z.string(),
  message: z.string(),
  payload: AdminFeatureJsonObjectSchema.default({}),
  status: z.string(),
  detected_at: Iso8601Schema,
  resolved_at: Iso8601Schema.nullable().default(null),
});
export type AdminFeatureDetailIssue = z.infer<typeof AdminFeatureDetailIssueSchema>;

export const AdminFeatureDetailOverrideSchema = z.object({
  override_id: z.string(),
  source_record_key: z.string().nullable().default(null),
  field_path: z.string(),
  source_value: z.unknown().nullable().default(null),
  override_value: z.unknown().nullable().default(null),
  prevent_provider_reactivation: z.boolean(),
  status: z.string(),
  reason: z.string().nullable().default(null),
  created_by: z.string().nullable().default(null),
  created_at: Iso8601Schema,
});
export type AdminFeatureDetailOverride = z.infer<typeof AdminFeatureDetailOverrideSchema>;

export const AdminFeatureDetailVersionSchema = z.object({
  feature_id: z.string(),
  version: z.number().int(),
  origin: z.string(),
  change_kind: z.string(),
  payload: AdminFeatureJsonObjectSchema.default({}),
  request_id: z.string().nullable().default(null),
  created_by: z.string().nullable().default(null),
  created_at: Iso8601Schema,
});
export type AdminFeatureDetailVersion = z.infer<typeof AdminFeatureDetailVersionSchema>;

export const AdminFeatureDetailFileSchema = z.object({
  file_id: z.string(),
  file_type: z.string(),
  storage_backend: z.string(),
  bucket: z.string(),
  object_key: z.string(),
  source_url: z.string().nullable().default(null),
  public_url: z.string().nullable().default(null),
  content_type: z.string().nullable().default(null),
  byte_size: z.number().int().nullable().default(null),
  checksum_sha256: z.string().nullable().default(null),
  width: z.number().int().nullable().default(null),
  height: z.number().int().nullable().default(null),
  role: z.string(),
  display_order: z.number().int(),
  alt_text: z.string().nullable().default(null),
  provider: z.string().nullable().default(null),
  dataset_key: z.string().nullable().default(null),
  source_record_key: z.string().nullable().default(null),
  payload: AdminFeatureJsonObjectSchema.default({}),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminFeatureDetailFile = z.infer<typeof AdminFeatureDetailFileSchema>;

export const AdminFeatureDetailSchema = z.object({
  feature: AdminFeatureDetailFeatureSchema,
  sources: z.array(AdminFeatureDetailSourceSchema).default([]),
  issues: z.array(AdminFeatureDetailIssueSchema).default([]),
  overrides: z.array(AdminFeatureDetailOverrideSchema).default([]),
  versions: z.array(AdminFeatureDetailVersionSchema).default([]),
  change_requests: z.array(AdminFeatureChangeRequestRecordSchema).default([]),
  files: z.array(AdminFeatureDetailFileSchema).default([]),
});
export type AdminFeatureDetail = z.infer<typeof AdminFeatureDetailSchema>;

/** 상세는 기본 마스킹, 사유 기반 원본 조회 시 audit 기록. */
export const AdminUserFileQuotaSchema = z.object({
  attachment_max_upload_bytes_override: z.number().int().gt(0).nullable().default(null),
  trip_attachment_quota_bytes_override: z.number().int().gt(0).nullable().default(null),
  user_attachment_quota_bytes_override: z.number().int().gt(0).nullable().default(null),
  effective_attachment_max_upload_bytes: z.number().int().gt(0).default(10 * 1024 * 1024),
  effective_trip_attachment_quota_bytes: z.number().int().gt(0).default(100 * 1024 * 1024),
  effective_user_attachment_quota_bytes: z.number().int().gt(0).default(1024 * 1024 * 1024),
});
export type AdminUserFileQuota = z.infer<typeof AdminUserFileQuotaSchema>;

export const AdminUserDetailSchema = AdminUserSummarySchema.extend({
  email: z.string(),
  email_revealed: z.boolean(),
  email_status: z.enum(['active', 'bounced', 'complained']),
  is_active: z.boolean(),
  avatar_url: z.string().nullable().default(null),
  avatar_kind: z.enum(['default', 'upload', 'external']).default('default'),
  avatar_content_type: z.string().nullable().default(null),
  avatar_byte_size: z.number().int().nullable().default(null),
  avatar_updated_at: Iso8601Schema.nullable().default(null),
  has_avatar: z.boolean().default(false),
  file_quota: AdminUserFileQuotaSchema.default({
    attachment_max_upload_bytes_override: null,
    trip_attachment_quota_bytes_override: null,
    user_attachment_quota_bytes_override: null,
    effective_attachment_max_upload_bytes: 10 * 1024 * 1024,
    effective_trip_attachment_quota_bytes: 100 * 1024 * 1024,
    effective_user_attachment_quota_bytes: 1024 * 1024 * 1024,
  }),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminUserDetail = z.infer<typeof AdminUserDetailSchema>;

/** force-verify / disable 등 위험 액션은 사유 필수. */
export const AdminActionRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type AdminActionRequest = z.infer<typeof AdminActionRequestSchema>;

export const AdminAvatarApplyRequestSchema = AvatarApplyRequestSchema.extend({
  access_reason: z.string().min(1).max(500),
});
export type AdminAvatarApplyRequest = z.infer<typeof AdminAvatarApplyRequestSchema>;

export const AdminAvatarDeleteRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type AdminAvatarDeleteRequest = z.infer<typeof AdminAvatarDeleteRequestSchema>;

export const AdminAvatarSettingsSchema = z.object({
  avatar_max_upload_bytes: z.number().int().gt(0),
});
export type AdminAvatarSettings = z.infer<typeof AdminAvatarSettingsSchema>;

export const AdminAvatarSettingsUpdateRequestSchema = z.object({
  avatar_max_upload_bytes: z.number().int().gt(0).max(104_857_600),
  access_reason: z.string().min(1).max(500),
});
export type AdminAvatarSettingsUpdateRequest = z.infer<
  typeof AdminAvatarSettingsUpdateRequestSchema
>;

export const AdminFileStorageSettingsSchema = z.object({
  attachment_max_upload_bytes: z.number().int().gt(0),
  trip_attachment_quota_bytes: z.number().int().gt(0),
  user_attachment_quota_bytes: z.number().int().gt(0),
});
export type AdminFileStorageSettings = z.infer<typeof AdminFileStorageSettingsSchema>;

export const AdminFileStorageSettingsUpdateRequestSchema = z.object({
  attachment_max_upload_bytes: z.number().int().gt(0).max(1_073_741_824),
  trip_attachment_quota_bytes: z.number().int().gt(0).max(10_737_418_240),
  user_attachment_quota_bytes: z.number().int().gt(0).max(109_951_162_777_600),
  access_reason: z.string().min(1).max(500),
});
export type AdminFileStorageSettingsUpdateRequest = z.infer<
  typeof AdminFileStorageSettingsUpdateRequestSchema
>;

export const AdminUserFileQuotaUpdateRequestSchema = z.object({
  attachment_max_upload_bytes_override: z.number().int().gt(0).nullable().default(null),
  trip_attachment_quota_bytes_override: z.number().int().gt(0).nullable().default(null),
  user_attachment_quota_bytes_override: z.number().int().gt(0).nullable().default(null),
  access_reason: z.string().min(1).max(500),
});
export type AdminUserFileQuotaUpdateRequest = z.infer<
  typeof AdminUserFileQuotaUpdateRequestSchema
>;

export const AdminPagedResponseSchema = z.object({
  items: z.array(AdminUserSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  limit: z.number().int(),
});
export type AdminPagedResponse = z.infer<typeof AdminPagedResponseSchema>;

export const AdminTripSummarySchema = z.object({
  trip_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  owner_email_masked: z.string(),
  title: z.string(),
  region_hint: z.string().nullable(),
  primary_region_code: z
    .string()
    .regex(/^[0-9]{2,10}$/)
    .nullable(),
  primary_region_source: TripPrimaryRegionSourceSchema.nullable(),
  start_date: z.string().date().nullable(),
  end_date: z.string().date().nullable(),
  visibility: TripVisibilitySchema,
  status: TripStatusSchema,
  version: z.number().int(),
  day_count: z.number().int(),
  poi_count: z.number().int(),
  companion_count: z.number().int(),
  share_link_count: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminTripSummary = z.infer<typeof AdminTripSummarySchema>;

export const AdminTripCompanionSummarySchema = z.object({
  companion_id: z.string().uuid(),
  user_id: z.string().uuid().nullable(),
  invited_email_masked: z.string().nullable(),
  invited_nickname: z.string().nullable(),
  role: z.enum(['co_owner', 'editor', 'viewer']),
  invited_at: Iso8601Schema,
  joined_at: Iso8601Schema.nullable(),
});
export type AdminTripCompanionSummary = z.infer<typeof AdminTripCompanionSummarySchema>;

export const AdminTripShareLinkSummarySchema = z.object({
  share_id: z.string().uuid(),
  visibility: z.enum(['view_only', 'comment', 'edit']),
  expires_at: Iso8601Schema.nullable(),
  revoked_at: Iso8601Schema.nullable(),
  last_used_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
});
export type AdminTripShareLinkSummary = z.infer<typeof AdminTripShareLinkSummarySchema>;

export const AdminTripDaySummarySchema = z.object({
  day_index: z.number().int(),
  date: z.string().date().nullable(),
  title: z.string().nullable(),
  note: z.string().nullable(),
  poi_count: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminTripDaySummary = z.infer<typeof AdminTripDaySummarySchema>;

export const AdminTripPoiSummarySchema = z.object({
  attachment_id: z.string().uuid(),
  day_index: z.number().int(),
  day_date: z.string().date().nullable(),
  day_title: z.string().nullable(),
  sort_order: z.string(),
  feature_id: z.string().nullable(),
  feature_label: z.string().nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  lon: z.number().nullable().default(null),
  lat: z.number().nullable().default(null),
  address_label: z.string().nullable().default(null),
  added_by_user_id: z.string().uuid(),
  added_by_email_masked: z.string().nullable(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  user_note: z.string().nullable(),
  budget_amount: NonNegativeDecimalStringSchema.nullable(),
  actual_amount: NonNegativeDecimalStringSchema.nullable(),
  currency: z.string(),
  user_url: z.string().nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminTripPoiSummary = z.infer<typeof AdminTripPoiSummarySchema>;

export const AdminTripDetailSchema = AdminTripSummarySchema.extend({
  description: z.string().nullable(),
  companions: z.array(AdminTripCompanionSummarySchema).default([]),
  days: z.array(AdminTripDaySummarySchema).default([]),
  pois: z.array(AdminTripPoiSummarySchema).default([]),
  attachments: z.array(AttachmentLibraryItemSchema).default([]),
  share_links: z.array(AdminTripShareLinkSummarySchema).default([]),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminTripDetail = z.infer<typeof AdminTripDetailSchema>;

export const AdminTripCreateRequestSchema = z
  .object({
    owner_user_id: z.string().uuid(),
    title: z.string().min(1).max(200),
    description: z.string().nullable().optional(),
    region_hint: z.string().max(120).nullable().optional(),
    primary_region_code: z
      .string()
      .regex(/^[0-9]{2,10}$/)
      .nullable()
      .optional(),
    start_date: z.string().date().nullable().optional(),
    end_date: z.string().date().nullable().optional(),
    visibility: TripVisibilitySchema.default('private'),
    status: TripStatusSchema.default('draft'),
    access_reason: z.string().min(1).max(500),
  })
  .superRefine((value, ctx) => {
    const hasStart = Boolean(value.start_date);
    const hasEnd = Boolean(value.end_date);
    if (hasStart !== hasEnd) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_date'],
        message: 'start_date와 end_date는 함께 입력해야 합니다.',
      });
      return;
    }
    if (value.start_date && value.end_date && value.end_date < value.start_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_date'],
        message: 'end_date는 start_date 이후여야 합니다.',
      });
    }
  });
export type AdminTripCreateRequest = z.infer<typeof AdminTripCreateRequestSchema>;

export const AdminTripPagedResponseSchema = z.object({
  items: z.array(AdminTripSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  limit: z.number().int(),
});
export type AdminTripPagedResponse = z.infer<typeof AdminTripPagedResponseSchema>;

export const AdminTripStatusRequestSchema = z.object({
  status: TripStatusSchema,
  access_reason: z.string().min(1).max(500),
});
export type AdminTripStatusRequest = z.infer<typeof AdminTripStatusRequestSchema>;

export const AdminOperationTargetSchema = z.enum(['trip', 'day', 'poi']);
export type AdminOperationTarget = z.infer<typeof AdminOperationTargetSchema>;

export const AdminOperationActionSchema = z.enum(['copy', 'move', 'delete']);
export type AdminOperationAction = z.infer<typeof AdminOperationActionSchema>;

export const AdminMoveDeletePolicySchema = z.enum(['move', 'delete', 'keep', 'orphan']);
export type AdminMoveDeletePolicy = z.infer<typeof AdminMoveDeletePolicySchema>;

export const AdminOperationPolicyOptionSchema = z.object({
  value: AdminMoveDeletePolicySchema,
  label: z.string(),
  allowed: z.boolean(),
  reason: z.string().nullable().default(null),
});
export type AdminOperationPolicyOption = z.infer<typeof AdminOperationPolicyOptionSchema>;

export const AdminOperationImpactSchema = z.object({
  target_type: AdminOperationTargetSchema,
  target_id: z.string().uuid().nullable().default(null),
  trip_id: z.string().uuid(),
  day_index: z.number().int().nullable().default(null),
  counts: z.record(z.string(), z.number().int()).default({}),
  policy_options: z.record(z.string(), z.array(AdminOperationPolicyOptionSchema)).default({}),
  warnings: z.array(z.string()).default([]),
});
export type AdminOperationImpact = z.infer<typeof AdminOperationImpactSchema>;

export const AdminOperationResultSchema = z.object({
  target_type: AdminOperationTargetSchema,
  action: AdminOperationActionSchema,
  source_trip_id: z.string().uuid(),
  target_trip_id: z.string().uuid().nullable().default(null),
  target_id: z.string().uuid().nullable().default(null),
  day_index: z.number().int().nullable().default(null),
  affected: z.record(z.string(), z.number().int()).default({}),
});
export type AdminOperationResult = z.infer<typeof AdminOperationResultSchema>;

export const AdminTripCopyRequestSchema = z.object({
  title: z.string().max(200).nullable().optional(),
  owner_user_id: z.string().uuid().nullable().optional(),
  scope: z.enum(['all', 'day', 'range']).default('all'),
  day_index: z.number().int().min(1).nullable().optional(),
  start_day_index: z.number().int().min(1).nullable().optional(),
  end_day_index: z.number().int().min(1).nullable().optional(),
  date_shift_days: z.number().int().min(-3650).max(3650).default(0),
  target_trip_id: z.string().uuid().nullable().optional(),
  access_reason: z.string().min(1).max(500),
});
export type AdminTripCopyRequest = z.infer<typeof AdminTripCopyRequestSchema>;

export const AdminTripMoveRequestSchema = z.object({
  owner_user_id: z.string().uuid(),
  access_reason: z.string().min(1).max(500),
});
export type AdminTripMoveRequest = z.infer<typeof AdminTripMoveRequestSchema>;

export const AdminTripDeleteRequestSchema = z.object({
  child_policy: z.enum(['keep', 'delete']).default('keep'),
  access_reason: z.string().min(1).max(500),
});
export type AdminTripDeleteRequest = z.infer<typeof AdminTripDeleteRequestSchema>;

export const AdminDayCopyRequestSchema = z.object({
  target_trip_id: z.string().uuid(),
  target_day_index: z.number().int().min(1),
  include_pois: z.boolean().default(true),
  include_attachments: z.boolean().default(true),
  access_reason: z.string().min(1).max(500),
});
export type AdminDayCopyRequest = z.infer<typeof AdminDayCopyRequestSchema>;

export const AdminDayMoveRequestSchema = z.object({
  target_trip_id: z.string().uuid(),
  target_day_index: z.number().int().min(1),
  poi_policy: z.enum(['move', 'delete']).default('move'),
  attachment_policy: z.enum(['move', 'delete']).default('move'),
  comment_policy: z.enum(['move', 'delete']).default('move'),
  access_reason: z.string().min(1).max(500),
});
export type AdminDayMoveRequest = z.infer<typeof AdminDayMoveRequestSchema>;

export const AdminDayDeleteRequestSchema = z.object({
  poi_policy: z.literal('delete').default('delete'),
  attachment_policy: z.literal('delete').default('delete'),
  comment_policy: z.literal('delete').default('delete'),
  access_reason: z.string().min(1).max(500),
});
export type AdminDayDeleteRequest = z.infer<typeof AdminDayDeleteRequestSchema>;

export const AdminPoiCopyRequestSchema = z.object({
  target_trip_id: z.string().uuid(),
  target_day_index: z.number().int().min(1),
  include_attachments: z.boolean().default(true),
  access_reason: z.string().min(1).max(500),
});
export type AdminPoiCopyRequest = z.infer<typeof AdminPoiCopyRequestSchema>;

export const AdminPoiMoveRequestSchema = z.object({
  target_trip_id: z.string().uuid(),
  target_day_index: z.number().int().min(1),
  attachment_policy: z.enum(['move', 'delete']).default('move'),
  comment_policy: z.enum(['move', 'delete']).default('move'),
  access_reason: z.string().min(1).max(500),
});
export type AdminPoiMoveRequest = z.infer<typeof AdminPoiMoveRequestSchema>;

export const AdminPoiDeleteRequestSchema = z.object({
  attachment_policy: z.literal('delete').default('delete'),
  comment_policy: z.literal('delete').default('delete'),
  access_reason: z.string().min(1).max(500),
});
export type AdminPoiDeleteRequest = z.infer<typeof AdminPoiDeleteRequestSchema>;

export const AdminPoiSummarySchema = z.object({
  attachment_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  trip_title: z.string(),
  owner_user_id: z.string().uuid(),
  owner_email_masked: z.string(),
  day_index: z.number().int(),
  sort_order: z.string(),
  feature_id: z.string().nullable(),
  feature_label: z.string().nullable(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminPoiSummary = z.infer<typeof AdminPoiSummarySchema>;

export const AdminPoiDetailSchema = AdminPoiSummarySchema.extend({
  added_by_user_id: z.string().uuid(),
  added_by_email_masked: z.string().nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  user_note: z.string().nullable(),
  budget_amount: NonNegativeDecimalStringSchema.nullable(),
  actual_amount: NonNegativeDecimalStringSchema.nullable(),
  currency: z.string(),
  user_url: z.string().nullable(),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminPoiDetail = z.infer<typeof AdminPoiDetailSchema>;

export const AdminPoiCreateRequestSchema = z.object({
  trip_id: z.string().uuid(),
  day_index: z.number().int().min(1),
  sort_order: z.string().min(1).max(80),
  feature_id: z.string().min(1).max(200).nullable().optional(),
  feature_snapshot: z.record(z.string(), z.unknown()).default({}),
  custom_marker_color: z
    .string()
    .regex(/^P-\d{2}$/)
    .nullable()
    .optional(),
  custom_marker_icon: z.string().max(64).nullable().optional(),
  planned_arrival_at: Iso8601Schema.nullable().optional(),
  planned_departure_at: Iso8601Schema.nullable().optional(),
  user_note: z.string().nullable().optional(),
  budget_amount: z.number().nonnegative().nullable().optional(),
  actual_amount: z.number().nonnegative().nullable().optional(),
  currency: z
    .string()
    .regex(/^[A-Z]{3}$/)
    .default('KRW'),
  user_url: z.string().max(2000).nullable().optional(),
  access_reason: z.string().min(1).max(500),
});
export type AdminPoiCreateRequest = z.infer<typeof AdminPoiCreateRequestSchema>;

export const AdminPoiPagedResponseSchema = z.object({
  items: z.array(AdminPoiSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  limit: z.number().int(),
});
export type AdminPoiPagedResponse = z.infer<typeof AdminPoiPagedResponseSchema>;

export const AdminPoiLinkStatusRequestSchema = z.object({
  broken: z.boolean(),
  access_reason: z.string().min(1).max(500),
});
export type AdminPoiLinkStatusRequest = z.infer<typeof AdminPoiLinkStatusRequestSchema>;

/** email_queue 행. */
export const AdminEmailEntrySchema = z.object({
  email_id: z.string().uuid(),
  to_email: z.string(),
  template: z.string(),
  status: z.enum(['pending', 'sent', 'delivered', 'bounced', 'complained', 'failed']),
  attempts: z.number().int(),
  last_error: z.string().nullable(),
  resend_id: z.string().nullable(),
  bounce_type: z.string().nullable(),
  scheduled_at: Iso8601Schema,
  sent_at: Iso8601Schema.nullable(),
});
export type AdminEmailEntry = z.infer<typeof AdminEmailEntrySchema>;

/** verify-chain 응답. */
export const AdminChainVerifySchema = z.object({
  valid: z.boolean(),
  broken_at: z.number().int().nullable(),
  rows_checked: z.number().int(),
});
export type AdminChainVerify = z.infer<typeof AdminChainVerifySchema>;

export const AdminBackupSnapshotRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type AdminBackupSnapshotRequest = z.infer<typeof AdminBackupSnapshotRequestSchema>;

export const AdminBackupSnapshotSchema = z.object({
  snapshot_id: z.string(),
  filename: z.string(),
  path: z.string(),
  size_bytes: z.number().int(),
  checksum_sha256: z.string().nullable(),
  status: z.enum(['available', 'verified']),
  created_at: Iso8601Schema,
});
export type AdminBackupSnapshot = z.infer<typeof AdminBackupSnapshotSchema>;

export const AdminBackupRestoreRequestSchema = z.object({
  snapshot_id: z.string().min(1).max(200),
  access_reason: z.string().min(1).max(500),
  confirm_schema_swap: z.boolean(),
});
export type AdminBackupRestoreRequest = z.infer<typeof AdminBackupRestoreRequestSchema>;

export const AdminBackupRestorePhaseSchema = z.object({
  name: z.enum(['preparing', 'restoring', 'validating', 'draining', 'switching']),
  status: z.enum(['pending', 'running', 'success', 'failed', 'skipped']),
  message: z.string().nullable(),
});
export type AdminBackupRestorePhase = z.infer<typeof AdminBackupRestorePhaseSchema>;

export const AdminBackupRestoreRunSchema = z.object({
  restore_id: z.string(),
  snapshot_id: z.string(),
  snapshot_path: z.string(),
  restore_schema: z.string(),
  previous_schema: z.string(),
  status: z.enum(['succeeded', 'failed']),
  phases: z.array(AdminBackupRestorePhaseSchema),
  started_at: Iso8601Schema,
  completed_at: Iso8601Schema,
});
export type AdminBackupRestoreRun = z.infer<typeof AdminBackupRestoreRunSchema>;
