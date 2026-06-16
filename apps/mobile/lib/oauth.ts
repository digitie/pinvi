import * as WebBrowser from 'expo-web-browser';
import type { MobileAuthResult } from '@pinvi/api-client';
import { ApiError } from '@pinvi/api-client';
import { api } from './api';

/**
 * 모바일 Google OAuth — 딥링크 1회용 code 흐름(백엔드 ADR-032/OAuth).
 *
 * 1) `/mobile/auth/oauth/google/start`로 authorize URL을 받고
 * 2) `WebBrowser.openAuthSessionAsync(url, 'pinvi://oauth')`로 인증 →
 *    백엔드 callback이 `pinvi://oauth?code=`(또는 `?error=`)로 리다이렉트하면 그 URL을 받는다.
 * 3) code를 `/mobile/auth/oauth/exchange`로 토큰과 교환한다.
 */
const REDIRECT_URL = 'pinvi://oauth';

export class OAuthCancelledError extends Error {
  constructor() {
    super('oauth-cancelled');
    this.name = 'OAuthCancelledError';
  }
}

export class OAuthProviderError extends Error {
  constructor(public code: string) {
    super(code);
    this.name = 'OAuthProviderError';
  }
}

export async function loginWithGoogle(): Promise<MobileAuthResult> {
  const { authorize_url } = await api.mobileAuth.oauthGoogleStart();

  const result = await WebBrowser.openAuthSessionAsync(authorize_url, REDIRECT_URL);
  if (result.type !== 'success' || !result.url) {
    // 'cancel' | 'dismiss' — 사용자가 닫음.
    throw new OAuthCancelledError();
  }

  const params = new URL(result.url).searchParams;
  const error = params.get('error');
  if (error) {
    throw new OAuthProviderError(error);
  }
  const code = params.get('code');
  if (!code) {
    throw new OAuthProviderError('OAUTH_CALLBACK_INVALID');
  }

  try {
    return await api.mobileAuth.oauthExchange(code);
  } catch (err) {
    if (err instanceof ApiError) {
      throw new OAuthProviderError(err.code);
    }
    throw err;
  }
}
