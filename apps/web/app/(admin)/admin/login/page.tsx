'use client';

import { Suspense, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { LoginRequestSchema } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { FormField } from '@/components/forms/FormField';
import { validateForm, type FieldErrors } from '@/lib/formValidation';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12501',
});

const ADMIN_ROLES = new Set(['admin', 'operator', 'cpo']);

export default function AdminLoginPage() {
  return (
    <Suspense fallback={null}>
      <AdminLoginForm />
    </Suspense>
  );
}

function AdminLoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const reason = search.get('reason');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(
    reason === 'forbidden' ? '관리자 권한이 필요합니다.' : null,
  );
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const focusField = (field: string | null) => {
    if (field === 'email') emailRef.current?.focus();
    else if (field === 'password') passwordRef.current?.focus();
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const result = validateForm(LoginRequestSchema, { email, password });
    setFieldErrors(result.fieldErrors);
    if (!result.success || !result.data) {
      focusField(result.firstField);
      return;
    }

    setLoading(true);
    try {
      const { user } = await authApi(apiClient).login(result.data);
      const hasAdmin = user.roles.some((r) => ADMIN_ROLES.has(r));
      if (!hasAdmin) {
        setError('관리자 권한이 없는 계정입니다.');
        await authApi(apiClient).logout().catch(() => undefined);
        return;
      }
      router.push('/admin');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'AUTH_INVALID_CREDENTIALS') {
          setError('이메일 또는 비밀번호가 올바르지 않습니다.');
        } else if (err.code === 'EMAIL_NOT_VERIFIED') {
          setError('이메일 인증이 필요합니다.');
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
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6 rounded-sm border border-hairline bg-white p-8">
        <header>
          <h1 className="text-xl font-bold text-ink">Pinvi Admin</h1>
          <p className="mt-1 text-xs text-muted">
            관리자/운영자/CPO 계정으로 로그인하세요.
          </p>
        </header>

        <form onSubmit={onSubmit} className="space-y-4" data-testid="admin-login-form" noValidate>
          <FormField
            ref={emailRef}
            id="admin-login-email"
            label="이메일"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={fieldErrors.email}
            data-testid="admin-login-email"
          />

          <FormField
            ref={passwordRef}
            id="admin-login-password"
            label="비밀번호"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={fieldErrors.password}
            data-testid="admin-login-password"
          />

          {error && (
            <p className="text-sm text-error-text" role="alert" data-testid="admin-login-error">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-sm bg-primary py-3 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-60"
            data-testid="admin-login-submit"
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  );
}
