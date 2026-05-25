'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { RegisterRequestSchema } from '@tripmate/schemas';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:8001',
});

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const parsed = RegisterRequestSchema.safeParse({ email, password, nickname });
    if (!parsed.success) {
      setError('입력 값을 다시 확인해 주세요. (비밀번호 최소 8자)');
      return;
    }

    setLoading(true);
    try {
      const result = await authApi(apiClient).register(parsed.data);
      router.push(
        `/signup/verify-pending?email=${encodeURIComponent(parsed.data.email)}&dispatched=${result.verification_email_dispatched}`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'EMAIL_ALREADY_USED') {
          setError('이미 가입된 이메일입니다.');
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
      <h1 className="text-2xl font-bold text-ink">회원가입</h1>

      <form onSubmit={onSubmit} className="space-y-4" data-testid="signup-form">
        <label className="block">
          <span className="text-sm text-ink">이메일</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="signup-email"
          />
        </label>

        <label className="block">
          <span className="text-sm text-ink">비밀번호 (8자 이상)</span>
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="signup-password"
          />
        </label>

        <label className="block">
          <span className="text-sm text-ink">닉네임</span>
          <input
            type="text"
            required
            maxLength={80}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            className="mt-1 w-full rounded-sm border border-hairline px-3 py-2 text-sm"
            data-testid="signup-nickname"
          />
        </label>

        {error && (
          <p className="text-sm text-error-text" data-testid="signup-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-sm bg-primary py-3 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-60"
          data-testid="signup-submit"
        >
          {loading ? '가입 중...' : '회원가입'}
        </button>
      </form>

      <p className="text-center text-xs text-muted">
        이미 계정이 있으신가요?{' '}
        <Link href="/login" className="text-primary underline">
          로그인
        </Link>
      </p>

      <p className="text-xs text-muted-soft">
        Sprint 1 단계 — 4 분리 동의 UI / 소셜 로그인은 Sprint 2에서 활성화. 회원가입 후 이메일
        인증을 거치면 프로필을 완성할 수 있습니다.
      </p>
    </div>
  );
}
