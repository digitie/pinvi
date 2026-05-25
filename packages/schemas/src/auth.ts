import { z } from 'zod';
import { Iso8601Schema } from './common.js';

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
export const AuthUserSchema = z.object({
  user_id: z.string().uuid(),
  email: z.string().email(),
  nickname: z.string().nullable(),
  avatar_url: z.string().url().nullable(),
  status: z.enum(['pending_verification', 'pending_profile', 'active', 'disabled']),
  roles: z.array(z.enum(['user', 'admin', 'operator', 'cpo'])),
  email_verified_at: Iso8601Schema.nullable(),
});
export type AuthUser = z.infer<typeof AuthUserSchema>;
