import { z } from 'zod';
import { Iso8601Schema } from './common';

/** 4 분리 동의 (위치정보법 + PIPA). `docs/compliance/lbs-act.md` §2.1. */
export const ConsentTypeSchema = z.enum([
  'tos',
  'privacy',
  'lbs_tos',
  'location_collection',
  'demographic_use',
  'marketing',
]);
export type ConsentType = z.infer<typeof ConsentTypeSchema>;

export const UserConsentSchema = z.object({
  consent_type: ConsentTypeSchema,
  version: z.string().min(1).max(32),
  agreed_at: Iso8601Schema,
  withdrawn_at: Iso8601Schema.nullable(),
});
export type UserConsent = z.infer<typeof UserConsentSchema>;

/** 프로필 완성 요청. `docs/api/auth.md` §4.1. */
export const ProfileCompleteRequestSchema = z.object({
  nickname: z.string().min(1).max(80),
  avatar_kind: z.enum(['default', 'upload']),
  avatar_attachment_id: z.string().uuid().nullable().optional(),
  gender: z.enum(['female', 'male', 'non_binary', 'no_answer']).nullable().optional(),
  birth_year_month: z
    .string()
    .regex(/^\d{6}$/, 'YYYYMM')
    .nullable()
    .optional(),
  residence_sigungu_code: z
    .string()
    .regex(/^\d{5}$/, '시군구 코드 5자리')
    .nullable()
    .optional(),
  consents: z.array(z.object({ consent_type: ConsentTypeSchema, version: z.string() })),
});
export type ProfileCompleteRequest = z.infer<typeof ProfileCompleteRequestSchema>;

const UserJsonObjectSchema = z.record(z.string(), z.unknown());

export const DsrRequestTypeSchema = z.enum(['access', 'correction', 'delete', 'suspend']);
export type DsrRequestType = z.infer<typeof DsrRequestTypeSchema>;

export const DsrRequestStatusSchema = z.enum([
  'received',
  'identity_check',
  'processing',
  'completed',
  'rejected',
  'withdrawn',
]);
export type DsrRequestStatus = z.infer<typeof DsrRequestStatusSchema>;

export const DsrRequestRecordSchema = z.object({
  request_id: z.string().uuid(),
  user_id: z.string().uuid().nullable().default(null),
  request_type: DsrRequestTypeSchema,
  status: DsrRequestStatusSchema,
  request_summary: z.string(),
  request_details: UserJsonObjectSchema.default({}),
  identity_proof_metadata: UserJsonObjectSchema.default({}),
  requester_email_masked: z.string(),
  assigned_cpo_user_id: z.string().uuid().nullable().default(null),
  received_at: Iso8601Schema,
  due_at: Iso8601Schema,
  identity_verified_at: Iso8601Schema.nullable().default(null),
  processing_started_at: Iso8601Schema.nullable().default(null),
  completed_at: Iso8601Schema.nullable().default(null),
  rejected_at: Iso8601Schema.nullable().default(null),
  withdrawn_at: Iso8601Schema.nullable().default(null),
  rejection_reason: z.string().nullable().default(null),
  result_summary: z.string().nullable().default(null),
  result_notice_hash: z.string().nullable().default(null),
  result_notice_email_id: z.string().uuid().nullable().default(null),
  export_manifest: UserJsonObjectSchema.default({}),
  partial_response: z.boolean().default(false),
  evidence_attachment_id: z.string().uuid().nullable().default(null),
  response_overdue: z.boolean().default(false),
  next_action: z.string(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type DsrRequestRecord = z.infer<typeof DsrRequestRecordSchema>;

export const DsrRequestListResponseSchema = z.object({
  items: z.array(DsrRequestRecordSchema).default([]),
  page_size: z.number().int(),
  total: z.number().int(),
});
export type DsrRequestListResponse = z.infer<typeof DsrRequestListResponseSchema>;

export const DsrRequestCreateRequestSchema = z.object({
  request_type: DsrRequestTypeSchema,
  request_summary: z.string().min(1).max(500),
  request_details: UserJsonObjectSchema.default({}),
});
export type DsrRequestCreateRequest = z.infer<typeof DsrRequestCreateRequestSchema>;

export const DsrRequestWithdrawRequestSchema = z.object({
  reason: z.string().max(500).nullable().optional(),
});
export type DsrRequestWithdrawRequest = z.infer<typeof DsrRequestWithdrawRequestSchema>;
