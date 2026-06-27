import { z } from 'zod';
import { Iso8601Schema } from './common';
import { ConsentTypeSchema } from './user';

const RequiredRegisterConsentTypes = new Set(['tos', 'privacy', 'lbs_tos', 'location_collection']);

const RegisterConsentItemSchema = z.object({
  consent_type: ConsentTypeSchema,
  version: z.string().min(1).max(32),
});

/** 회원가입 요청. `docs/api/auth.md` §2.1. */
export const RegisterRequestSchema = z
  .object({
    email: z.string().email().max(320),
    password: z.string().min(8).max(200),
    nickname: z.string().min(1).max(80),
    consents: z.array(RegisterConsentItemSchema).min(1),
  })
  .superRefine((value, ctx) => {
    const provided = new Set<string>();
    for (const item of value.consents) {
      if (provided.has(item.consent_type)) {
        ctx.addIssue({
          code: 'custom',
          path: ['consents'],
          message: `동의 항목 중복: ${item.consent_type}`,
        });
        return;
      }
      provided.add(item.consent_type);
    }

    for (const consentType of RequiredRegisterConsentTypes) {
      if (!provided.has(consentType)) {
        ctx.addIssue({
          code: 'custom',
          path: ['consents'],
          message: `필수 동의 누락: ${consentType}`,
        });
      }
    }
  });
export type RegisterRequest = z.infer<typeof RegisterRequestSchema>;

/** 회원가입 응답. */
export const RegisterResponseSchema = z.object({
  user: z.object({
    user_id: z.string().uuid(),
    email: z.string().email(),
    status: z.enum(['pending_verification', 'pending_profile', 'active', 'disabled']),
    email_verified_at: Iso8601Schema.nullable(),
  }),
  verification_email_dispatched: z.boolean(),
});

/** 이메일 verify 요청. */
export const VerifyEmailRequestSchema = z.object({
  token: z.string().length(43),
});

/** 인증(재인증) 메일 재발송 요청. */
export const VerifyEmailResendRequestSchema = z.object({
  email: z.string().email(),
});
export type VerifyEmailResendRequest = z.infer<typeof VerifyEmailResendRequestSchema>;

/** 인증 메일 재발송 응답. enumeration 방지를 위해 항상 accepted=true. */
export const VerifyEmailResendResponseSchema = z.object({
  accepted: z.boolean(),
});
export type VerifyEmailResendResponse = z.infer<typeof VerifyEmailResendResponseSchema>;

/** 로그인 요청. */
export const LoginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

/** /auth/me 응답 user. */
export const AuthUserOAuthIdentitySchema = z.object({
  provider: z.enum(['google', 'naver', 'kakao']),
  provider_email: z.string().max(320).nullable(),
  provider_email_verified: z.boolean().nullable(),
  display_name: z.string().nullable(),
  linked_at: Iso8601Schema,
  last_login_at: Iso8601Schema.nullable(),
});

export const AuthUserSchema = z.object({
  user_id: z.string().uuid(),
  email: z.string().max(320),
  nickname: z.string().nullable(),
  avatar_url: z.string().url().nullable(),
  avatar_kind: z.enum(['default', 'upload', 'external']).default('default'),
  avatar_content_type: z.string().nullable().default(null),
  avatar_byte_size: z.number().int().nullable().default(null),
  avatar_updated_at: Iso8601Schema.nullable().default(null),
  has_avatar: z.boolean().default(false),
  status: z.enum(['pending_verification', 'pending_profile', 'active', 'disabled']),
  roles: z.array(z.enum(['user', 'admin', 'operator', 'cpo'])),
  email_verified_at: Iso8601Schema.nullable(),
  has_password: z.boolean(),
  oauth_identities: z.array(AuthUserOAuthIdentitySchema).default([]),
});
export type AuthUser = z.infer<typeof AuthUserSchema>;
export type AuthUserOAuthIdentity = z.infer<typeof AuthUserOAuthIdentitySchema>;

/** OAuth provider 목록. */
export const OAuthProviderNameSchema = z.enum(['google', 'naver', 'kakao']);
export const OAuthProviderSchema = z.object({
  provider: OAuthProviderNameSchema,
  enabled: z.boolean(),
});
export const OAuthProvidersResponseSchema = z.object({
  providers: z.array(OAuthProviderSchema),
});
export type OAuthProvider = z.infer<typeof OAuthProviderSchema>;
export type OAuthProvidersResponse = z.infer<typeof OAuthProvidersResponseSchema>;

/** OAuth authorize URL 발급 요청/응답. */
export const OAuthStartRequestSchema = z.object({
  return_to: z
    .string()
    .regex(/^\/[\w/_\-?=&]*$/)
    .default('/'),
  mode: z.enum(['login', 'link']).default('login'),
});
export const OAuthStartResponseSchema = z.object({
  authorize_url: z.string().url(),
});
export type OAuthStartRequest = z.infer<typeof OAuthStartRequestSchema>;
export type OAuthStartResponse = z.infer<typeof OAuthStartResponseSchema>;

export const OAuthLinkRequestSchema = z.object({
  return_to: z
    .string()
    .regex(/^\/[\w/_\-?=&]*$/)
    .default('/profile'),
});
export type OAuthLinkRequest = z.infer<typeof OAuthLinkRequestSchema>;
