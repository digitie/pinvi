'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:12501',
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
    <div className="space-y-6 text-sm">
      <h1 className="text-2xl font-bold text-ink">이메일 인증</h1>
      <p className="text-muted">인증 처리 중입니다…</p>
    </div>
  );
}

function VerifyEmailContent() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get('token');
  const [status, setStatus] = useState<'pending' | 'success' | 'error'>('pending');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setError('인증 토큰이 없습니다.');
      return;
    }

    void (async () => {
      try {
        await authApi(apiClient).verifyEmail({ token });
        setStatus('success');
        // 3초 후 trips로 이동 (현재는 / 로 — Sprint 4 진입 후 /trips)
        setTimeout(() => router.push('/'), 3000);
      } catch (err) {
        setStatus('error');
        if (err instanceof ApiError) {
          setError(err.code === 'VALIDATION_ERROR' ? '토큰이 잘못되었거나 만료되었습니다.' : err.message);
        } else {
          setError('알 수 없는 오류가 발생했습니다.');
        }
      }
    })();
  }, [token, router]);

  return (
    <div className="space-y-6 text-sm">
      <h1 className="text-2xl font-bold text-ink">이메일 인증</h1>

      {status === 'pending' && <p className="text-muted">인증 처리 중입니다…</p>}
      {status === 'success' && (
        <p className="text-ink" data-testid="verify-success">
          인증이 완료되었습니다. 잠시 후 메인으로 이동합니다.
        </p>
      )}
      {status === 'error' && (
        <>
          <p className="text-error-text" data-testid="verify-error">
            {error}
          </p>
          <Link href="/login" className="text-primary underline">
            로그인 화면으로
          </Link>
        </>
      )}
    </div>
  );
}
