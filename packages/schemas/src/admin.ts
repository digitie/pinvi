import { z } from 'zod';
import { Iso8601Schema } from './common';
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

/** 상세는 기본 마스킹, 사유 기반 원본 조회 시 audit 기록. */
export const AdminUserDetailSchema = AdminUserSummarySchema.extend({
  email: z.string(),
  email_revealed: z.boolean(),
  email_status: z.enum(['active', 'bounced', 'complained']),
  is_active: z.boolean(),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminUserDetail = z.infer<typeof AdminUserDetailSchema>;

/** force-verify / disable 등 위험 액션은 사유 필수. */
export const AdminActionRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type AdminActionRequest = z.infer<typeof AdminActionRequestSchema>;

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

export const AdminTripDetailSchema = AdminTripSummarySchema.extend({
  description: z.string().nullable(),
  companions: z.array(AdminTripCompanionSummarySchema).default([]),
  share_links: z.array(AdminTripShareLinkSummarySchema).default([]),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminTripDetail = z.infer<typeof AdminTripDetailSchema>;

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

export const AdminPoiSummarySchema = z.object({
  attachment_id: z.string().uuid(),
  trip_id: z.string().uuid(),
  trip_title: z.string(),
  owner_user_id: z.string().uuid(),
  owner_email_masked: z.string(),
  day_index: z.number().int(),
  sort_order: z.string(),
  feature_id: z.string(),
  feature_label: z.string().nullable(),
  feature_link_broken_at: Iso8601Schema.nullable(),
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type AdminPoiSummary = z.infer<typeof AdminPoiSummarySchema>;

const AdminPoiAmountSchema = z.union([z.string(), z.number()]).nullable();

export const AdminPoiDetailSchema = AdminPoiSummarySchema.extend({
  added_by_user_id: z.string().uuid(),
  added_by_email_masked: z.string().nullable(),
  feature_snapshot: z.record(z.string(), z.unknown()),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  planned_arrival_at: Iso8601Schema.nullable(),
  planned_departure_at: Iso8601Schema.nullable(),
  user_note: z.string().nullable(),
  budget_amount: AdminPoiAmountSchema,
  actual_amount: AdminPoiAmountSchema,
  currency: z.string(),
  user_url: z.string().nullable(),
  recent_audit: z.array(AdminAuditEntrySchema).default([]),
});
export type AdminPoiDetail = z.infer<typeof AdminPoiDetailSchema>;

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
