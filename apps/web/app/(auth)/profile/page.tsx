'use client';

import { useEffect, useMemo, useState } from 'react';
import { Link2, Loader2, Unlink } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { AuthUser, OAuthProvider } from '@tripmate/schemas';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:12501',
});

function formatDateTime(value: string | null) {
  if (!value) {
    return '기록 없음';
  }
  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

const PROFILE_OAUTH_ERROR_MESSAGES: Record<string, string> = {
  OAUTH_ACCOUNT_LINK_REQUIRED:
    '이 Google 계정은 다른 TripMate 계정과 충돌합니다. 연결할 계정을 다시 확인해 주세요.',
  OAUTH_EMAIL_UNVERIFIED:
    'Google 계정의 이메일 인증을 확인할 수 없습니다. Google 이메일 인증 후 다시 연결해 주세요.',
  OAUTH_PROVIDER_ERROR: 'Google 계정 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.',
  OAUTH_STATE_INVALID: 'Google 연결 요청이 만료되었습니다. 다시 시작해 주세요.',
};

function getProfileOAuthErrorMessage(code: string) {
  return PROFILE_OAUTH_ERROR_MESSAGES[code] ?? 'Google 연결을 완료하지 못했습니다.';
}

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<AuthUser | null>(null);
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<'link-google' | 'unlink-google' | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const googleIdentity = useMemo(
    () => me?.oauth_identities.find((identity) => identity.provider === 'google') ?? null,
    [me],
  );
  const googleEnabled = providers.some((provider) => provider.provider === 'google' && provider.enabled);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = authApi(apiClient);
      const [user, oauthProviders] = await Promise.all([api.me(), api.oauthProviders()]);
      setMe(user);
      setProviders(oauthProviders.providers);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        router.replace('/login');
        return;
      }
      setError(err instanceof ApiError ? err.message : '프로필을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('error');
    if (code) {
      setError(getProfileOAuthErrorMessage(code));
      window.history.replaceState(null, '', window.location.pathname);
    }
  }, []);

  const onLinkGoogle = async () => {
    setAction('link-google');
    setError(null);
    setMessage(null);
    try {
      const result = await authApi(apiClient).linkGoogleOAuth({ return_to: '/profile' });
      window.location.assign(result.authorize_url);
    } catch (err) {
      if (err instanceof ApiError && err.code in PROFILE_OAUTH_ERROR_MESSAGES) {
        setError(getProfileOAuthErrorMessage(err.code));
      } else {
        setError(err instanceof ApiError ? err.message : 'Google 연결을 시작하지 못했습니다.');
      }
      setAction(null);
    }
  };

  const onUnlinkGoogle = async () => {
    if (!window.confirm('Google 연결을 해제할까요?')) {
      return;
    }
    setAction('unlink-google');
    setError(null);
    setMessage(null);
    try {
      await authApi(apiClient).unlinkGoogleOAuth();
      setMessage('Google 연결을 해제했습니다.');
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OAUTH_UNLINK_PASSWORD_REQUIRED') {
        setError('비밀번호가 없는 계정은 Google 연결을 해제할 수 없습니다.');
      } else {
        setError(err instanceof ApiError ? err.message : 'Google 연결을 해제하지 못했습니다.');
      }
    } finally {
      setAction(null);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-40 items-center justify-center text-sm text-muted">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        불러오는 중...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-ink">프로필</h1>
        {me && (
          <p className="text-sm text-muted">
            {me.email} · {me.nickname ?? '닉네임 없음'}
          </p>
        )}
      </header>

      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
          {message}
        </p>
      )}
      {error && (
        <p className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text" data-testid="profile-error">
          {error}
        </p>
      )}

      <section className="space-y-3 rounded-sm border border-hairline bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink">Google</h2>
            <p className="mt-1 text-xs text-muted" data-testid="google-oauth-status">
              {googleIdentity
                ? `${googleIdentity.provider_email ?? '이메일 없음'} · 연결 ${formatDateTime(
                    googleIdentity.linked_at,
                  )}`
                : '연결되지 않음'}
            </p>
          </div>

          {googleIdentity ? (
            <button
              type="button"
              onClick={onUnlinkGoogle}
              disabled={action !== null || !me?.has_password}
              className="inline-flex shrink-0 items-center gap-2 rounded-sm border border-error-text px-3 py-2 text-sm font-semibold text-error-text disabled:opacity-50"
              data-testid="google-oauth-unlink"
            >
              {action === 'unlink-google' ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Unlink className="h-4 w-4" aria-hidden="true" />
              )}
              해제
            </button>
          ) : (
            <button
              type="button"
              onClick={onLinkGoogle}
              disabled={action !== null || !googleEnabled}
              className="inline-flex shrink-0 items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="google-oauth-link"
            >
              {action === 'link-google' ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Link2 className="h-4 w-4" aria-hidden="true" />
              )}
              연결
            </button>
          )}
        </div>

        {googleIdentity && !me?.has_password && (
          <p className="text-xs text-muted">
            비밀번호를 먼저 설정해야 Google 연결을 해제할 수 있습니다.
          </p>
        )}
      </section>
    </div>
  );
}
