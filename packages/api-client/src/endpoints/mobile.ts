import {
  AuthUserSchema,
  LoginRequestSchema,
  OAuthStartResponseSchema,
  VerifyEmailRequestSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

/**
 * 모바일 인증 응답 — 웹은 httpOnly cookie(ADR-032)지만 모바일은 토큰을 본문으로 받아
 * SecureStore에 보관한다 (백엔드 `/mobile/auth/*`, expo-implementation-plan §5 #2).
 */
export const MobileAuthResponseSchema = z.object({
  user: AuthUserSchema,
  access_token: z.string(),
  refresh_token: z.string(),
  expires_at: z.string(),
});
export type MobileAuthResult = z.infer<typeof MobileAuthResponseSchema>;

/** `/mobile/auth/*` — 토큰 본문 발급(모바일 Bearer). */
export const mobileAuthApi = (client: ApiClient) => ({
  login: (body: z.infer<typeof LoginRequestSchema>) =>
    client.request('/mobile/auth/login', {
      method: 'POST',
      body: JSON.stringify(LoginRequestSchema.parse(body)),
      schema: MobileAuthResponseSchema,
    }),

  verifyEmail: (body: z.infer<typeof VerifyEmailRequestSchema>) =>
    client.request('/mobile/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify(VerifyEmailRequestSchema.parse(body)),
      schema: MobileAuthResponseSchema,
    }),

  refresh: (refreshToken: string) =>
    client.request('/mobile/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      schema: MobileAuthResponseSchema,
    }),

  logout: (refreshToken: string) =>
    client.requestNoContent('/mobile/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),

  /** Google OAuth 시작 — authorize URL 발급(앱 딥링크로 callback). */
  oauthGoogleStart: () =>
    client.request('/mobile/auth/oauth/google/start', {
      method: 'POST',
      schema: OAuthStartResponseSchema,
    }),

  /** 딥링크로 받은 1회용 code를 토큰과 교환. */
  oauthExchange: (code: string) =>
    client.request('/mobile/auth/oauth/exchange', {
      method: 'POST',
      body: JSON.stringify({ code }),
      schema: MobileAuthResponseSchema,
    }),
});
