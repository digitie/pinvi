import { z } from 'zod';
import { Iso8601Schema } from './common';

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
export type AdminBackupSnapshotRequest = z.infer<
  typeof AdminBackupSnapshotRequestSchema
>;

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
