'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { LoginRequestSchema } from '@tripmate/schemas';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:8001',
});

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

      <p className="text-center text-xs text-muted">
        소셜 로그인 (Google / 네이버 / 카카오)은 Sprint 2에 활성화됩니다.
      </p>
    </div>
  );
}
