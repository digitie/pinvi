'use client';

/* eslint-disable @next/next/no-img-element */

import { type ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
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
import { buttonClassName } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

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

// URL의 `?error=` 쿼리로 전달되는 OAuth 콜백 오류 — 마운트 시 1회만 읽으면 되는 순수 파생값이므로
// effect 대신 초기 state 계산에서 바로 읽는다(react-hooks/set-state-in-effect). URL 정리(history
// replaceState)는 별도의, setState 없는 effect로 남긴다.
function readProfileOAuthErrorFromLocation(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  const code = params.get('error');
  if (!code) {
    return null;
  }
  return getProfileOAuthErrorMessage(code, parseOAuthProvider(params.get('provider')));
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
  const [error, setError] = useState<string | null>(readProfileOAuthErrorFromLocation);
  // 파괴적 액션 확인 — native confirm 대신 공용 다이얼로그(DESIGN.md 확인 정책).
  const [pendingConfirm, setPendingConfirm] = useState<
    { kind: 'unlink'; provider: OAuthProviderName } | { kind: 'avatar' } | null
  >(null);
  const confirmTriggerRef = useRef<HTMLElement | null>(null);
  const accountSectionRef = useRef<HTMLDivElement | null>(null);

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

  // 마운트 시 loading 초기값이 이미 true이므로 여기서 다시 setLoading(true)를 호출할 필요는
  // 없다 — 수동 재호출(unlink/avatar 액션 후 새로고침) 지점에서 직접 setLoading(true)를 부른다.
  // setError(null)도 reload()를 부르는 각 핸들러(onUnlinkProvider/onAvatarFile/onDeleteAvatar)가
  // 자신의 try 진입 전 이미 스스로 초기화하므로 여기서는 지운다 — 마운트 경로에서 지우지 않으면
  // URL의 OAuth 오류로 채워진 초기 error state를 이 함수가 곧바로 덮어써 버린다
  // (react-hooks/set-state-in-effect: 마운트 effect가 이 함수를 호출할 때 동기 setState가
  // 걸리는 것도 함께 피한다).
  const reload = async () => {
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
    void (async () => {
      await reload();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // 오류 메시지 자체는 초기 state(readProfileOAuthErrorFromLocation)에서 이미 읽었다 — 여기서는
    // 쿼리스트링을 지우는 history 정리만 한다(설정 없음 → setState 없는 순수 side effect).
    const params = new URLSearchParams(window.location.search);
    if (params.get('error')) {
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

  // 파괴적 액션은 공용 확인 다이얼로그로만 확인한다(DESIGN.md 확인 정책, native confirm 금지).
  const requestUnlink = (provider: OAuthProviderName, trigger: HTMLElement | null) => {
    confirmTriggerRef.current = trigger;
    setError(null);
    setMessage(null);
    setPendingConfirm({ kind: 'unlink', provider });
  };

  const requestDeleteAvatar = (trigger: HTMLElement | null) => {
    confirmTriggerRef.current = trigger;
    setError(null);
    setMessage(null);
    setPendingConfirm({ kind: 'avatar' });
  };

  const onUnlinkProvider = async (provider: OAuthProviderName) => {
    const label = OAUTH_PROVIDER_LABELS[provider];
    setAction(`unlink-${provider}`);
    setError(null);
    setMessage(null);
    try {
      await authApi(apiClient).unlinkOAuth(provider);
      setMessage(`${label} 연결을 해제했습니다.`);
      setLoading(true);
      await reload();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OAUTH_UNLINK_PASSWORD_REQUIRED') {
        setError(`비밀번호가 없는 계정은 ${label} 연결을 해제할 수 없습니다.`);
      } else {
        setError(err instanceof ApiError ? err.message : `${label} 연결을 해제하지 못했습니다.`);
      }
    } finally {
      setAction(null);
      setPendingConfirm(null);
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
      setLoading(true);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 저장하지 못했습니다.');
    } finally {
      setAvatarAction(null);
    }
  };

  const onDeleteAvatar = async () => {
    setAvatarAction('delete');
    setError(null);
    setMessage(null);
    try {
      await authApi(apiClient).deleteAvatar();
      setMessage('아바타를 삭제했습니다.');
      setLoading(true);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 삭제하지 못했습니다.');
    } finally {
      setAvatarAction(null);
      // 삭제 성공 시 트리거(삭제 버튼)가 disabled로 바뀐다 — 포커스는 섹션이 받는다.
      if (!confirmTriggerRef.current?.isConnected) confirmTriggerRef.current = accountSectionRef.current;
      // 요청이 끝난 뒤 닫는다 — busy 표시와 포커스 복원을 살리기 위해(T-315 5차 리뷰 패턴).
      setPendingConfirm(null);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-40 items-center justify-center text-sm text-muted">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
        불러오는 중…
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
        className="space-y-3 rounded-sm border border-hairline bg-canvas p-4"
        data-testid="profile-avatar-section"
      >
        {/* 삭제 성공 후 트리거가 사라지거나 비활성이면 포커스가 이 컨테이너로 돌아온다. */}
        <div
          ref={accountSectionRef}
          tabIndex={-1}
          className="flex flex-col gap-4 outline-hidden sm:flex-row sm:items-center sm:justify-between"
        >
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
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-sm bg-cta px-3 py-2 text-sm font-semibold text-on-primary hover:bg-cta-hover">
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
              onClick={(event) => requestDeleteAvatar(event.currentTarget)}
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
            className="space-y-3 rounded-sm border border-hairline bg-canvas p-4"
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
                  onClick={(event) => requestUnlink(provider, event.currentTarget)}
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
                  className={buttonClassName({ size: 'sm', className: 'shrink-0' })}
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

      <ConfirmDialog
        open={pendingConfirm != null}
        tone="danger"
        title={
          pendingConfirm?.kind === 'unlink'
            ? `${OAUTH_PROVIDER_LABELS[pendingConfirm.provider]} 연결을 해제할까요?`
            : '아바타 이미지를 삭제할까요?'
        }
        description={
          pendingConfirm?.kind === 'unlink'
            ? '다시 연결하려면 해당 서비스에서 인증을 다시 거쳐야 합니다.'
            : '삭제하면 되돌릴 수 없습니다.'
        }
        confirmLabel={pendingConfirm?.kind === 'unlink' ? '연결 해제' : '삭제'}
        cancelLabel="취소"
        busy={action !== null || avatarAction !== null}
        onConfirm={() => {
          const target = pendingConfirm;
          if (!target) return;
          if (target.kind === 'unlink') void onUnlinkProvider(target.provider);
          else void onDeleteAvatar();
        }}
        onCancel={() => setPendingConfirm(null)}
        returnFocusRef={confirmTriggerRef}
        testId="profile-destructive-confirm"
      />
    </div>
  );
}
