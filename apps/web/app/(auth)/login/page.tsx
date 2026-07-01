'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoginRequestSchema } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { FormField } from '@/components/forms/FormField';
import { validateForm, type FieldErrors } from '@pinvi/domain';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

type OAuthProviderName = 'google' | 'naver' | 'kakao';

const DISABLED_OAUTH_PROVIDERS: Record<OAuthProviderName, boolean> = {
  google: false,
  naver: false,
  kakao: false,
};

const OAUTH_PROVIDER_LABELS: Record<OAuthProviderName, string> = {
  google: 'Google',
  naver: 'Naver',
  kakao: 'Kakao',
};

function parseOAuthProvider(provider: string | null): OAuthProviderName {
  if (provider === 'naver' || provider === 'kakao') {
    return provider;
  }
  return 'google';
}

function getOAuthErrorMessage(code: string, provider: OAuthProviderName = 'google') {
  const label = OAUTH_PROVIDER_LABELS[provider];
  const messages: Record<string, string> = {
    OAUTH_ACCOUNT_LINK_REQUIRED: `이미 같은 이메일의 Pinvi 계정이 있습니다. 이메일로 로그인한 뒤 프로필에서 ${label}을 연결해 주세요.`,
    OAUTH_CALLBACK_INVALID: `${label} 로그인 응답이 올바르지 않습니다. 다시 시도해 주세요.`,
    OAUTH_EMAIL_UNVERIFIED: `${label} 계정의 이메일 인증을 확인할 수 없습니다. 인증 메일 또는 provider 이메일 설정을 확인해 주세요.`,
    OAUTH_PROVIDER_DENIED: `${label} 로그인이 취소되었습니다.`,
    OAUTH_PROVIDER_ERROR: `${label} 계정 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.`,
    OAUTH_STATE_INVALID: `${label} 로그인 요청이 만료되었습니다. 다시 시작해 주세요.`,
  };
  return messages[code] ?? `${label} 로그인을 완료하지 못했습니다.`;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const [oauthProviders, setOauthProviders] = useState(DISABLED_OAUTH_PROVIDERS);
  const [oauthLoading, setOauthLoading] = useState<OAuthProviderName | null>(null);
  const [oauthProvidersLoading, setOauthProvidersLoading] = useState(true);
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendNotice, setResendNotice] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('error');
    if (code) {
      setOauthError(getOAuthErrorMessage(code, parseOAuthProvider(params.get('provider'))));
    }
  }, []);

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
          if (provider.provider in next) {
            next[provider.provider] = provider.enabled;
          }
        }
        setOauthProviders(next);
      } catch {
        if (active) {
          setOauthError((current) => current ?? '소셜 로그인 상태를 불러오지 못했습니다.');
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

  const focusField = (field: string | null) => {
    if (field === 'email') emailRef.current?.focus();
    else if (field === 'password') passwordRef.current?.focus();
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setUnverifiedEmail(null);
    setResendNotice(null);

    const result = validateForm(LoginRequestSchema, { email, password });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      focusField(result.firstField);
      return;
    }

    setLoading(true);
    try {
      await authApi(apiClient).login(result.data);
      router.push('/trips');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'EMAIL_NOT_VERIFIED') {
          const dispatched = err.details?.verification_email_dispatched === true;
          setUnverifiedEmail(result.data.email);
          setError(
            dispatched
              ? '이메일 인증이 필요합니다. 인증 메일을 다시 보냈어요. 메일함(스팸함)을 확인해 주세요.'
              : '이메일 인증이 필요합니다. 메일함을 확인하시고, 받지 못했다면 아래에서 다시 보낼 수 있어요.',
          );
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

  const onResend = async () => {
    if (!unverifiedEmail) return;
    setResendLoading(true);
    setResendNotice(null);
    try {
      await authApi(apiClient).resendVerification({ email: unverifiedEmail });
      setResendNotice('인증 메일을 보냈어요. 메일함(스팸함)을 확인해 주세요.');
    } catch {
      setResendNotice('재발송에 실패했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setResendLoading(false);
    }
  };

  const onOAuthStart = async (provider: OAuthProviderName) => {
    setOauthError(null);
    setOauthLoading(provider);
    const label = OAUTH_PROVIDER_LABELS[provider];
    try {
      const result = await authApi(apiClient).startOAuth(provider, {
        return_to: '/trips',
        mode: 'login',
      });
      window.location.assign(result.authorize_url);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'OAUTH_NOT_CONFIGURED') {
        setOauthError(`${label} 로그인이 아직 설정되지 않았습니다.`);
      } else if (err instanceof ApiError) {
        setOauthError(err.message);
      } else {
        setOauthError(`${label} 로그인을 시작하지 못했습니다.`);
      }
    } finally {
      setOauthLoading(null);
    }
  };

  const oauthDisabled = (provider: OAuthProviderName) =>
    oauthProvidersLoading || !oauthProviders[provider] || oauthLoading !== null;
  const visibleOAuthProviders = (['google', 'naver', 'kakao'] as const).filter(
    (provider) => oauthProvidersLoading || oauthProviders[provider],
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-ink">로그인</h1>

      <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form" noValidate>
        <FormField
          ref={emailRef}
          id="login-email"
          label="이메일"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          data-testid="login-email"
        />

        <FormField
          ref={passwordRef}
          id="login-password"
          label="비밀번호"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          data-testid="login-password"
        />

        {error && (
          <p className="text-sm text-error-text" role="alert" data-testid="login-error">
            {error}
          </p>
        )}

        {unverifiedEmail && (
          <div
            className="space-y-2 rounded-sm border border-hairline bg-surface p-3"
            data-testid="resend-verification"
          >
            <button
              type="button"
              onClick={onResend}
              disabled={resendLoading}
              className="text-sm font-semibold text-primary underline disabled:opacity-60"
              data-testid="resend-verification-button"
            >
              {resendLoading ? '인증 메일 보내는 중...' : '인증 메일 다시 보내기'}
            </button>
            {resendNotice && (
              <p
                className="text-xs text-muted"
                role="status"
                data-testid="resend-verification-notice"
              >
                {resendNotice}
              </p>
            )}
          </div>
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

        {visibleOAuthProviders.map((provider) => {
          const label = OAUTH_PROVIDER_LABELS[provider];
          return (
            <button
              key={provider}
              type="button"
              disabled={oauthDisabled(provider)}
              onClick={() => onOAuthStart(provider)}
              className="flex w-full items-center justify-center gap-2 rounded-sm border border-hairline bg-white px-3 py-3 text-sm font-semibold text-ink hover:bg-surface disabled:opacity-60"
              data-testid={`${provider}-oauth-start`}
              aria-busy={oauthLoading === provider}
            >
              <span
                className="flex h-5 w-5 items-center justify-center rounded-full border border-hairline text-xs font-bold"
                aria-hidden="true"
              >
                {label[0]}
              </span>
              {oauthLoading === provider ? `${label} 연결 중...` : `${label}로 시작`}
            </button>
          );
        })}
      </div>
    </div>
  );
}
