import {
  AvatarApplyRequestSchema,
  AvatarInfoSchema,
  AvatarUploadUrlRequestSchema,
  AttachmentLibraryPageSchema,
  AuthUserSchema,
  DownloadUrlResponseSchema,
  LoginRequestSchema,
  OAuthLinkRequestSchema,
  OAuthProviderNameSchema,
  OAuthProvidersResponseSchema,
  OAuthStartRequestSchema,
  OAuthStartResponseSchema,
  RegisterRequestSchema,
  RegisterResponseSchema,
  UploadUrlResponseSchema,
  VerifyEmailRequestSchema,
  VerifyEmailResendRequestSchema,
  VerifyEmailResendResponseSchema,
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

  resendVerification: (body: z.infer<typeof VerifyEmailResendRequestSchema>) =>
    client.request('/auth/verify-email/resend', {
      method: 'POST',
      body: JSON.stringify(VerifyEmailResendRequestSchema.parse(body)),
      schema: VerifyEmailResendResponseSchema,
    }),

  login: (body: z.infer<typeof LoginRequestSchema>) =>
    client.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(LoginRequestSchema.parse(body)),
      schema: AuthUserSchema,
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

  createAvatarUploadUrl: (body: z.infer<typeof AvatarUploadUrlRequestSchema>) =>
    client.request('/users/me/avatar/upload-url', {
      method: 'POST',
      body: JSON.stringify(AvatarUploadUrlRequestSchema.parse(body)),
      schema: UploadUrlResponseSchema,
    }),

  updateAvatar: (body: z.infer<typeof AvatarApplyRequestSchema>) =>
    client.request('/users/me/avatar', {
      method: 'PUT',
      body: JSON.stringify(AvatarApplyRequestSchema.parse(body)),
      schema: AvatarInfoSchema,
    }),

  getAvatarDownloadUrl: () =>
    client.request('/users/me/avatar/download-url', {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  deleteAvatar: () =>
    client.request('/users/me/avatar', {
      method: 'DELETE',
      schema: AvatarInfoSchema,
    }),

  listFiles: (params: { page?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.page) qs.set('page', String(params.page));
    if (params.limit) qs.set('limit', String(params.limit));
    return client.request(`/users/me/files${qs.toString() ? `?${qs.toString()}` : ''}`, {
      method: 'GET',
      schema: AttachmentLibraryPageSchema,
    });
  },

  fileDownloadUrl: (attachmentId: string) =>
    client.request(`/users/me/files/${attachmentId}/download-url`, {
      method: 'GET',
      schema: DownloadUrlResponseSchema,
    }),

  deleteFile: (attachmentId: string) =>
    client.requestNoContent(`/users/me/files/${attachmentId}`, {
      method: 'DELETE',
    }),

  oauthProviders: () =>
    client.request('/auth/oauth/providers', {
      method: 'GET',
      schema: OAuthProvidersResponseSchema,
    }),

  startOAuth: (
    provider: z.infer<typeof OAuthProviderNameSchema>,
    body: z.infer<typeof OAuthStartRequestSchema>,
  ) =>
    client.request(`/auth/oauth/${provider}/start`, {
      method: 'POST',
      body: JSON.stringify(OAuthStartRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  startGoogleOAuth: (body: z.infer<typeof OAuthStartRequestSchema>) =>
    client.request('/auth/oauth/google/start', {
      method: 'POST',
      body: JSON.stringify(OAuthStartRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  linkOAuth: (
    provider: z.infer<typeof OAuthProviderNameSchema>,
    body: z.infer<typeof OAuthLinkRequestSchema>,
  ) =>
    client.request(`/auth/oauth/${provider}/link`, {
      method: 'POST',
      body: JSON.stringify(OAuthLinkRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  linkGoogleOAuth: (body: z.infer<typeof OAuthLinkRequestSchema>) =>
    client.request('/auth/oauth/google/link', {
      method: 'POST',
      body: JSON.stringify(OAuthLinkRequestSchema.parse(body)),
      schema: OAuthStartResponseSchema,
    }),

  unlinkOAuth: (provider: z.infer<typeof OAuthProviderNameSchema>) =>
    client.requestNoContent(`/auth/oauth/${provider}`, {
      method: 'DELETE',
    }),

  unlinkGoogleOAuth: () =>
    client.requestNoContent('/auth/oauth/google', {
      method: 'DELETE',
    }),
});
