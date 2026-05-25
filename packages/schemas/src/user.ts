import { z } from 'zod';
import { Iso8601Schema } from './common.js';

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
