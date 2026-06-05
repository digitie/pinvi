import { z } from 'zod';
import { Iso8601Schema } from './common';

/** 회원가입 요청. `docs/api/auth.md` §2.1. */
export const RegisterRequestSchema = z.object({
  email: z.string().email().max(320),
  password: z.string().min(8).max(200),
  nickname: z.string().min(1).max(80),
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
  return_to: z.string().regex(/^\/[\w/_\-?=&]*$/).default('/'),
  mode: z.enum(['login', 'link']).default('login'),
});
export const OAuthStartResponseSchema = z.object({
  authorize_url: z.string().url(),
});
export type OAuthStartRequest = z.infer<typeof OAuthStartRequestSchema>;
export type OAuthStartResponse = z.infer<typeof OAuthStartResponseSchema>;

export const OAuthLinkRequestSchema = z.object({
  return_to: z.string().regex(/^\/[\w/_\-?=&]*$/).default('/profile'),
});
export type OAuthLinkRequest = z.infer<typeof OAuthLinkRequestSchema>;
