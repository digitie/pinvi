'use client';

/* eslint-disable @next/next/no-img-element */

import { type ChangeEvent, useEffect, useMemo, useState } from 'react';
import { ImageIcon, Link2, Loader2, Trash2, Unlink, Upload } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { AuthUser, OAuthProvider } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import {
  IMAGE_UPLOAD_CONTENT_TYPES,
  allowedUploadMessage,
  contentTypeFromFile,
  isAllowedUploadContentType,
  putToPresigned,
} from '@pinvi/domain';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
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

type OAuthProviderName = OAuthProvider['provider'];

const OAUTH_PROVIDER_NAMES: OAuthProviderName[] = ['google', 'naver', 'kakao'];
const OAUTH_PROVIDER_LABELS: Record<OAuthProviderName, string> = {
  google: 'Google',
  naver: 'Naver',
  kakao: 'Kakao',
};

const PROFILE_OAUTH_ERROR_CODES = new Set([
  'OAUTH_ACCOUNT_LINK_REQUIRED',
  'OAUTH_EMAIL_UNVERIFIED',
  'OAUTH_PROVIDER_ERROR',
  'OAUTH_STATE_INVALID',
]);

function parseOAuthProvider(provider: string | null): OAuthProviderName {
  if (provider === 'naver' || provider === 'kakao') {
    return provider;
  }
  return 'google';
}

function getProfileOAuthErrorMessage(code: string, provider: OAuthProviderName = 'google') {
  const label = OAUTH_PROVIDER_LABELS[provider];
  const messages: Record<string, string> = {
    OAUTH_ACCOUNT_LINK_REQUIRED: `${label} 계정은 다른 Pinvi 계정과 충돌합니다. 연결할 계정을 다시 확인해 주세요.`,
    OAUTH_EMAIL_UNVERIFIED: `${label} 계정의 이메일 인증을 확인할 수 없습니다. 인증 메일 또는 provider 이메일 설정을 확인해 주세요.`,
    OAUTH_PROVIDER_ERROR: `${label} 계정 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.`,
    OAUTH_STATE_INVALID: `${label} 연결 요청이 만료되었습니다. 다시 시작해 주세요.`,
  };
  return messages[code] ?? `${label} 연결을 완료하지 못했습니다.`;
}

function formatBytes(value: number | null | undefined) {
  if (!value) {
    return '크기 기록 없음';
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<AuthUser | null>(null);
  const [providers, setProviders] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<
    `link-${OAuthProviderName}` | `unlink-${OAuthProviderName}` | null
  >(null);
  const [avatarAction, setAvatarAction] = useState<'upload' | 'delete' | null>(null);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const oauthIdentities = useMemo(
    () =>
      Object.fromEntries(
        OAUTH_PROVIDER_NAMES.map((provider) => [
          provider,
          me?.oauth_identities.find((identity) => identity.provider === provider) ?? null,
        ]),
      ) as Record<OAuthProviderName, AuthUser['oauth_identities'][number] | null>,
    [me],
  );
  const enabledProviders = useMemo(
    () =>
      Object.fromEntries(
        OAUTH_PROVIDER_NAMES.map((providerName) => [
          providerName,
          providers.some((provider) => provider.provider === providerName && provider.enabled),
        ]),
      ) as Record<OAuthProviderName, boolean>,
    [providers],
  );

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = authApi(apiClient);
      const [user, oauthProviders] = await Promise.all([api.me(), api.oauthProviders()]);
      let nextAvatarSrc: string | null = null;
      if (user.has_avatar) {
        try {
          const avatar = await api.getAvatarDownloadUrl();
          nextAvatarSrc = avatar.public_url ?? avatar.download_url;
        } catch {
          nextAvatarSrc = null;
        }
      }
      setMe(user);
      setProviders(oauthProviders.providers);
      setAvatarSrc(nextAvatarSrc);
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
    const params = new URLSearchParams(window.location.search);
    const code = params.get('error');
    if (code) {
      setError(getProfileOAuthErrorMessage(code, parseOAuthProvider(params.get('provider'))));
      window.history.replaceState(null, '', window.location.pathname);
    }
  }, []);

  const onLinkProvider = async (provider: OAuthProviderName) => {
    const label = OAUTH_PROVIDER_LABELS[provider];
    setAction(`link-${provider}`);
    setError(null);
    setMessage(null);
    try {
      const result = await authApi(apiClient).linkOAuth(provider, { return_to: '/profile' });
      window.location.assign(result.authorize_url);
    } catch (err) {
      if (err instanceof ApiError && PROFILE_OAUTH_ERROR_CODES.has(err.code)) {
        setError(getProfileOAuthErrorMessage(err.code, provider));
      } else {
        setError(err instanceof ApiError ? err.message : `${label} 연결을 시작하지 못했습니다.`);
      }
      setAction(null);
    }
  };

  const onUnlinkProvider = async (provider: OAuthProviderName) => {
    const label = OAUTH_PROVIDER_LABELS[provider];
    if (!window.confirm(`${label} 연결을 해제할까요?`)) {
      return;
    }
    setAction(`unlink-${provider}`);
    setError(null);
    setMessage(null);
    try {
      await authApi(apiClient).unlinkOAuth(provider);
      setMessage(`${label} 연결을 해제했습니다.`);
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OAUTH_UNLINK_PASSWORD_REQUIRED') {
        setError(`비밀번호가 없는 계정은 ${label} 연결을 해제할 수 없습니다.`);
      } else {
        setError(err instanceof ApiError ? err.message : `${label} 연결을 해제하지 못했습니다.`);
      }
    } finally {
      setAction(null);
    }
  };

  const onAvatarFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = '';
    if (!file) return;
    const contentType = contentTypeFromFile(file);
    if (!isAllowedUploadContentType(contentType, IMAGE_UPLOAD_CONTENT_TYPES)) {
      setError(allowedUploadMessage(IMAGE_UPLOAD_CONTENT_TYPES));
      return;
    }
    setAvatarAction('upload');
    setError(null);
    setMessage(null);
    try {
      const api = authApi(apiClient);
      const upload = await api.createAvatarUploadUrl({
        filename: file.name,
        content_type: contentType,
        content_length: file.size,
      });
      await putToPresigned(upload, file);
      await api.updateAvatar({
        bucket: upload.bucket,
        storage_key: upload.storage_key,
        content_type: contentType,
        byte_size: file.size,
        public_url: upload.public_url ?? null,
      });
      setMessage('아바타를 저장했습니다.');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 저장하지 못했습니다.');
    } finally {
      setAvatarAction(null);
    }
  };

  const onDeleteAvatar = async () => {
    if (!window.confirm('아바타 이미지를 삭제할까요?')) {
      return;
    }
    setAvatarAction('delete');
    setError(null);
    setMessage(null);
    try {
      await authApi(apiClient).deleteAvatar();
      setMessage('아바타를 삭제했습니다.');
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 삭제하지 못했습니다.');
    } finally {
      setAvatarAction(null);
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
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="profile-error"
        >
          {error}
        </p>
      )}

      <section
        className="space-y-3 rounded-sm border border-hairline bg-white p-4"
        data-testid="profile-avatar-section"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            {avatarSrc ? (
              <img
                src={avatarSrc}
                alt=""
                className="h-16 w-16 rounded-full border border-hairline object-cover"
                data-testid="profile-avatar-image"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-full border border-hairline bg-surface-soft text-muted">
                <ImageIcon className="h-6 w-6" aria-hidden="true" />
              </div>
            )}
            <div>
              <h2 className="text-sm font-semibold text-ink">아바타</h2>
              <p className="mt-1 text-xs text-muted" data-testid="profile-avatar-meta">
                {me?.has_avatar
                  ? `${me.avatar_content_type ?? 'image'} · ${formatBytes(me.avatar_byte_size)}`
                  : '등록된 이미지 없음'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-white">
              {avatarAction === 'upload' ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Upload className="h-4 w-4" aria-hidden="true" />
              )}
              {me?.has_avatar ? '교체' : '업로드'}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="sr-only"
                disabled={avatarAction !== null}
                onChange={onAvatarFile}
                data-testid="profile-avatar-input"
              />
            </label>
            <button
              type="button"
              disabled={!me?.has_avatar || avatarAction !== null}
              onClick={onDeleteAvatar}
              className="inline-flex items-center gap-2 rounded-sm border border-error-text px-3 py-2 text-sm font-semibold text-error-text disabled:opacity-50"
              data-testid="profile-avatar-delete"
            >
              {avatarAction === 'delete' ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              )}
              삭제
            </button>
          </div>
        </div>
      </section>

      {OAUTH_PROVIDER_NAMES.map((provider) => {
        const label = OAUTH_PROVIDER_LABELS[provider];
        const identity = oauthIdentities[provider];
        const linkAction = `link-${provider}` as const;
        const unlinkAction = `unlink-${provider}` as const;
        return (
          <section
            key={provider}
            className="space-y-3 rounded-sm border border-hairline bg-white p-4"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-ink">{label}</h2>
                <p className="mt-1 text-xs text-muted" data-testid={`${provider}-oauth-status`}>
                  {identity
                    ? `${identity.provider_email ?? '이메일 없음'} · 연결 ${formatDateTime(
                        identity.linked_at,
                      )}`
                    : '연결되지 않음'}
                </p>
              </div>

              {identity ? (
                <button
                  type="button"
                  onClick={() => onUnlinkProvider(provider)}
                  disabled={action !== null || !me?.has_password}
                  className="inline-flex shrink-0 items-center gap-2 rounded-sm border border-error-text px-3 py-2 text-sm font-semibold text-error-text disabled:opacity-50"
                  data-testid={`${provider}-oauth-unlink`}
                >
                  {action === unlinkAction ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Unlink className="h-4 w-4" aria-hidden="true" />
                  )}
                  해제
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => onLinkProvider(provider)}
                  disabled={action !== null || !enabledProviders[provider]}
                  className="inline-flex shrink-0 items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  data-testid={`${provider}-oauth-link`}
                >
                  {action === linkAction ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Link2 className="h-4 w-4" aria-hidden="true" />
                  )}
                  연결
                </button>
              )}
            </div>

            {identity && !me?.has_password && (
              <p className="text-xs text-muted">
                비밀번호를 먼저 설정해야 {label} 연결을 해제할 수 있습니다.
              </p>
            )}
          </section>
        );
      })}
    </div>
  );
}
