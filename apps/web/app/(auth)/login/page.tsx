'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoginRequestSchema } from '@tripmate/schemas';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:9021',
});

type OAuthProviderName = 'google' | 'naver' | 'kakao';

const DISABLED_OAUTH_PROVIDERS: Record<OAuthProviderName, boolean> = {
  google: false,
  naver: false,
  kakao: false,
};

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [oauthProviders, setOauthProviders] = useState(DISABLED_OAUTH_PROVIDERS);
  const [oauthLoading, setOauthLoading] = useState<OAuthProviderName | null>(null);
  const [oauthProvidersLoading, setOauthProvidersLoading] = useState(true);
  const [oauthError, setOauthError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const loadProviders = async () => {
      try {
        const result = await authApi(apiClient).oauthProviders();
        if (!active) {
          return;
        }
        const next = { ...DISABLED_OAUTH_PROVIDERS };
        for (const provider of result.providers) {
          next[provider.provider] = provider.enabled;
        }
        setOauthProviders(next);
      } catch {
        if (active) {
          setOauthError('소셜 로그인 상태를 불러오지 못했습니다.');
        }
      } finally {
        if (active) {
          setOauthProvidersLoading(false);
        }
      }
    };

    void loadProviders();

    return () => {
      active = false;
    };
  }, []);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const parsed = LoginRequestSchema.safeParse({ email, password });
    if (!parsed.success) {
      setError('이메일 또는 비밀번호 형식을 확인해 주세요.');
      return;
    }

    setLoading(true);
    try {
      await authApi(apiClient).login(parsed.data);
      router.push('/trips');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'EMAIL_NOT_VERIFIED') {
          setError('이메일 인증이 필요합니다. 메일을 확인해 주세요.');
        } else if (err.code === 'AUTH_INVALID_CREDENTIALS') {
          setError('이메일 또는 비밀번호가 올바르지 않습니다.');
        } else {
          setError(err.message);
        }
      } else {
        setError('알 수 없는 오류가 발생했습니다.');
      }
    } finally {
      setLoading(false);
    }
  };

  const onGoogleStart = async () => {
    setOauthError(null);
    setOauthLoading('google');
    try {
      const result = await authApi(apiClient).startGoogleOAuth({
        return_to: '/trips',
        mode: 'login',
      });
      window.location.assign(result.authorize_url);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OAUTH_NOT_CONFIGURED') {
        setOauthError('Google 로그인이 아직 설정되지 않았습니다.');
      } else if (err instanceof ApiError) {
        setOauthError(err.message);
      } else {
        setOauthError('Google 로그인을 시작하지 못했습니다.');
      }
    } finally {
      setOauthLoading(null);
    }
  };

  const googleOAuthDisabled =
    oauthProvidersLoading || !oauthProviders.google || oauthLoading !== null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-ink">로그인</h1>

      <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
        <label className="block">
          <span className="text-sm text-ink">이메일</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="login-email"
          />
        </label>

        <label className="block">
          <span className="text-sm text-ink">비밀번호</span>
          <input
            type="password"
            required
            minLength={1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="login-password"
          />
        </label>

        {error && (
          <p className="text-sm text-error-text" data-testid="login-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-sm bg-primary py-3 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-60"
          data-testid="login-submit"
        >
          {loading ? '로그인 중...' : '로그인'}
        </button>
      </form>

      <p className="text-center text-xs text-muted">
        계정이 없으신가요?{' '}
        <Link href="/signup" className="text-primary underline">
          회원가입
        </Link>
      </p>

      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-hairline" />
        <span className="text-xs text-muted">또는</span>
        <span className="h-px flex-1 bg-hairline" />
      </div>

      <div className="space-y-2">
        {oauthError && (
          <p className="text-sm text-error-text" data-testid="oauth-error">
            {oauthError}
          </p>
        )}

        <button
          type="button"
          disabled={googleOAuthDisabled}
          onClick={onGoogleStart}
          className="flex w-full items-center justify-center gap-2 rounded-sm border border-hairline bg-white px-3 py-3 text-sm font-semibold text-ink hover:bg-surface disabled:opacity-60"
          data-testid="google-oauth-start"
          aria-busy={oauthLoading === 'google'}
        >
          <span
            className="flex h-5 w-5 items-center justify-center rounded-full border border-hairline text-xs font-bold"
            aria-hidden="true"
          >
            G
          </span>
          {oauthLoading === 'google' ? 'Google 연결 중...' : 'Google로 시작'}
        </button>
      </div>
    </div>
  );
}
