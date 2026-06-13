import {
  AuthUserSchema,
  LoginRequestSchema,
  OAuthLinkRequestSchema,
  OAuthProvidersResponseSchema,
  OAuthStartRequestSchema,
  OAuthStartResponseSchema,
  RegisterRequestSchema,
  RegisterResponseSchema,
  VerifyEmailRequestSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

export const authApi = (client: ApiClient) => ({
  register: (body: z.infer<typeof RegisterRequestSchema>) =>
    client.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(RegisterRequestSchema.parse(body)),
      schema: RegisterResponseSchema,
    }),

  verifyEmail: (body: z.infer<typeof VerifyEmailRequestSchema>) =>
    client.request('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify(VerifyEmailRequestSchema.parse(body)),
      schema: z.object({
        user: AuthUserSchema,
        access_token_dispatched: z.boolean(),
      }),
    }),

  login: (body: z.infer<typeof LoginRequestSchema>) =>
    client.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(LoginRequestSchema.parse(body)),
      schema: z.object({ user: AuthUserSchema }),
    }),

  refresh: () =>
    client.request('/auth/refresh', {
      method: 'POST',
      schema: AuthUserSchema,
    }),

  logout: () =>
    client.requestNoContent('/auth/logout', {
      method: 'POST',
    }),

  me: () =>
    client.request('/auth/me', {
      method: 'GET',
      schema: AuthUserSchema,
    }),

  oauthProviders: () =>
    client.request('/auth/oauth/providers', {
      method: 'GET',
      schema: OAuthProvidersResponseSchema,
    }),

  startGoogleOAuth: (body: z.infer<typeof OAuthStartRequestSchema>) =>
    client.request('/auth/oauth/google/start', {
      method: 'POST',
      body: JSON.stringify(OAuthStartRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  linkGoogleOAuth: (body: z.infer<typeof OAuthLinkRequestSchema>) =>
    client.request('/auth/oauth/google/link', {
      method: 'POST',
      body: JSON.stringify(OAuthLinkRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  unlinkGoogleOAuth: () =>
    client.requestNoContent('/auth/oauth/google', {
      method: 'DELETE',
    }),
});
