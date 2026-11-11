'use client';

import { ButtonLink } from '@/components/ui/Button';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerifyEmailPending />}>
      <VerifyEmailContent />
    </Suspense>
  );
}

function VerifyEmailPending() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-ink">이메일 인증</h1>
      <p className="text-base text-muted" role="status" aria-live="polite">
        인증 처리 중입니다…
      </p>
    </div>
  );
}

function VerifyEmailContent() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get('token');
  // token 유무는 useSearchParams()로 렌더 중에 이미 알 수 있는 값이므로, "토큰 없음" 상태는
  // effect에서 setState하지 않고 초기 state 계산에서 바로 반영한다(react-hooks/set-state-in-effect).
  const [status, setStatus] = useState<'pending' | 'success' | 'error'>(
    token ? 'pending' : 'error',
  );
  const [error, setError] = useState<string | null>(token ? null : '인증 토큰이 없습니다.');

  useEffect(() => {
    if (!token) {
      return;
    }

    let active = true;
    void (async () => {
      try {
        await authApi(apiClient).verifyEmail({ token });
        if (!active) return;
        setStatus('success');
        // 인증 완료 3초 후 홈으로(로그인은 별도) — 안내 문구와 동일.
      } catch (err) {
        if (!active) return;
        setStatus('error');
        if (err instanceof ApiError) {
          setError(
            err.code === 'VALIDATION_ERROR' ? '토큰이 잘못되었거나 만료되었습니다.' : err.message,
          );
        } else {
          setError('알 수 없는 오류가 발생했습니다.');
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  useEffect(() => {
    if (status !== 'success') return;
    const timer = setTimeout(() => router.push('/'), 3000);
    return () => clearTimeout(timer);
  }, [status, router]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-ink">이메일 인증</h1>

      {status === 'pending' && (
        <p className="text-base text-muted" role="status" aria-live="polite">
          인증 처리 중입니다…
        </p>
      )}
      {status === 'success' && (
        <p className="text-base text-ink" role="status" data-testid="verify-success">
          인증이 완료되었습니다. 잠시 후 메인으로 이동합니다.
        </p>
      )}
      {status === 'error' && (
        <>
          <p className="text-base text-error-text" role="alert" data-testid="verify-error">
            {error}
          </p>
          <ButtonLink href="/login" variant="secondary">
            로그인 화면으로
          </ButtonLink>
        </>
      )}
    </div>
  );
}
