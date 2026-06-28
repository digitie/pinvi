import { z } from 'zod';
import { Iso8601Schema } from './common';

const ModerationJsonObjectSchema = z.record(z.string(), z.unknown());

export const ContentReportTargetTypeSchema = z.enum([
  'trip',
  'comment',
  'attachment',
  'share_link',
]);
export type ContentReportTargetType = z.infer<typeof ContentReportTargetTypeSchema>;

export const ContentReportReasonCodeSchema = z.enum([
  'spam',
  'harassment',
  'privacy',
  'illegal',
  'safety',
  'other',
]);
export type ContentReportReasonCode = z.infer<typeof ContentReportReasonCodeSchema>;

export const ContentReportStatusSchema = z.enum([
  'received',
  'reviewing',
  'hidden',
  'taken_down',
  'rejected',
  'appealed',
  'restored',
]);
export type ContentReportStatus = z.infer<typeof ContentReportStatusSchema>;

export const ContentModerationActionTypeSchema = z.enum([
  'review',
  'hide',
  'takedown',
  'restore',
  'reject',
  'appeal',
]);
export type ContentModerationActionType = z.infer<typeof ContentModerationActionTypeSchema>;

export const ContentModerationActionRecordSchema = z.object({
  action_id: z.string().uuid(),
  report_id: z.string().uuid(),
  actor_user_id: z.string().uuid().nullable().default(null),
  action: ContentModerationActionTypeSchema,
  action_reason: z.string(),
  before_state: ModerationJsonObjectSchema.default({}),
  after_state: ModerationJsonObjectSchema.default({}),
  created_at: Iso8601Schema,
});
export type ContentModerationActionRecord = z.infer<typeof ContentModerationActionRecordSchema>;

export const ContentReportRecordSchema = z.object({
  report_id: z.string().uuid(),
  target_type: ContentReportTargetTypeSchema,
  target_id: z.string().uuid(),
  target_trip_id: z.string().uuid().nullable().default(null),
  target_owner_user_id: z.string().uuid().nullable().default(null),
  reporter_user_id: z.string().uuid().nullable().default(null),
  reason_code: ContentReportReasonCodeSchema,
  reason_text: z.string(),
  status: ContentReportStatusSchema,
  target_snapshot: ModerationJsonObjectSchema.default({}),
  evidence: ModerationJsonObjectSchema.default({}),
  reviewer_user_id: z.string().uuid().nullable().default(null),
  resolution_summary: z.string().nullable().default(null),
  appeal_summary: z.string().nullable().default(null),
  reviewed_at: Iso8601Schema.nullable().default(null),
  actioned_at: Iso8601Schema.nullable().default(null),
  appealed_at: Iso8601Schema.nullable().default(null),
  restored_at: Iso8601Schema.nullable().default(null),
  next_actions: z.array(ContentModerationActionTypeSchema).default([]),
  actions: z.array(ContentModerationActionRecordSchema).default([]),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type ContentReportRecord = z.infer<typeof ContentReportRecordSchema>;

export const ContentReportListResponseSchema = z.object({
  items: z.array(ContentReportRecordSchema).default([]),
  page_size: z.number().int(),
  total: z.number().int(),
});
export type ContentReportListResponse = z.infer<typeof ContentReportListResponseSchema>;

export const ContentReportCreateRequestSchema = z.object({
  target_type: ContentReportTargetTypeSchema,
  target_id: z.string().uuid(),
  reason_code: ContentReportReasonCodeSchema,
  reason_text: z.string().min(1).max(2000),
  evidence: ModerationJsonObjectSchema.default({}),
});
export type ContentReportCreateRequest = z.infer<typeof ContentReportCreateRequestSchema>;

export const ContentReportAppealRequestSchema = z.object({
  appeal_reason: z.string().min(1).max(2000),
});
export type ContentReportAppealRequest = z.infer<typeof ContentReportAppealRequestSchema>;

export const ContentModerationActionRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
  resolution_summary: z.string().min(1).max(2000),
});
export type ContentModerationActionRequest = z.infer<typeof ContentModerationActionRequestSchema>;
