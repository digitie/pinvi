import { z } from 'zod';
import { CoordSchema, Iso8601Schema } from './common';
import {
  ExternalRefSchema,
  FeatureKindSchema,
  FeatureRequestStatusSchema,
  FeatureRequestTypeSchema,
} from './feature';

/** Admin feature-request 검토 큐 1건 (요청자 이메일은 마스킹). */
export const AdminFeatureRequestSummarySchema = z.object({
  request_id: z.string().uuid(),
  requester_user_id: z.string().uuid(),
  requester_email_masked: z.string().nullable().optional(),
  type: FeatureRequestTypeSchema,
  kind: FeatureKindSchema,
  name: z.string(),
  coord: CoordSchema,
  categories: z.array(z.string()),
  note: z.string().nullable().optional(),
  target_feature_id: z.string().nullable().optional(),
  source: z.string().default('user'),
  external_ref: ExternalRefSchema.nullable().default(null),
  status: FeatureRequestStatusSchema,
  kor_travel_map_ref: z.record(z.string(), z.unknown()).nullable().optional(),
  reviewed_by_admin_id: z.string().uuid().nullable().optional(),
  created_at: Iso8601Schema,
  resolved_at: Iso8601Schema.nullable().optional(),
});
export type AdminFeatureRequestSummary = z.infer<typeof AdminFeatureRequestSummarySchema>;

export const AdminFeatureRequestPagedResponseSchema = z.object({
  items: z.array(AdminFeatureRequestSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  limit: z.number().int(),
});
export type AdminFeatureRequestPagedResponse = z.infer<
  typeof AdminFeatureRequestPagedResponseSchema
>;

/** 승인 입력 — new_place는 category(8자리)/marker_color/marker_icon이 필수(서버 422). */
export const AdminFeatureRequestApproveSchema = z.object({
  access_reason: z.string().min(1).max(500),
  category: z.string().max(32).optional(),
  marker_color: z
    .string()
    .regex(/^P-\d{2}$/, 'marker color는 P-01~P-16 형식.')
    .optional(),
  marker_icon: z.string().max(64).optional(),
  name: z.string().min(1).max(200).optional(),
  kor_travel_map_reason: z.string().max(500).optional(),
});
export type AdminFeatureRequestApprove = z.infer<typeof AdminFeatureRequestApproveSchema>;

export const AdminFeatureRequestRejectSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type AdminFeatureRequestReject = z.infer<typeof AdminFeatureRequestRejectSchema>;

export const AdminFeatureRequestResultSchema = z.object({
  request_id: z.string().uuid(),
  status: FeatureRequestStatusSchema,
  kor_travel_map_ref: z.record(z.string(), z.unknown()).nullable().optional(),
  reviewed_by_admin_id: z.string().uuid().nullable().optional(),
  resolved_at: Iso8601Schema.nullable().optional(),
});
export type AdminFeatureRequestResult = z.infer<typeof AdminFeatureRequestResultSchema>;
