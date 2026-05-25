import {
  AuthUserSchema,
  LoginRequestSchema,
  RegisterRequestSchema,
  RegisterResponseSchema,
  VerifyEmailRequestSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client.js';

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
      schema: z.object({}).passthrough(),
    }),

  logout: () =>
    client.request('/auth/logout', {
      method: 'POST',
      schema: z.object({}).passthrough(),
    }),

  me: () =>
    client.request('/auth/me', {
      method: 'GET',
      schema: AuthUserSchema,
    }),
});
