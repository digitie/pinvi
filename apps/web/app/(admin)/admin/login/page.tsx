'use client';

import { Suspense, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { LoginForm, type LoginSubmission } from '@kor-travel/ui';
import { LoginRequestSchema } from '@pinvi/schemas';
import { ApiClient, ApiError, authApi } from '@pinvi/api-client';
import { validateForm } from '@pinvi/domain';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
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
  const queryClient = useQueryClient();
  const search = useSearchParams();
  const formHost = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(
    search.get('reason') === 'forbidden' ? '관리자 권한이 필요합니다.' : null,
  );
  function clearError() {
    setError(null);
    formHost.current
      ?.querySelectorAll('[aria-invalid]')
      .forEach((node) => node.removeAttribute('aria-invalid'));
  }
  async function submit({ credentials }: LoginSubmission) {
    const result = validateForm(LoginRequestSchema, {
      email: credentials.username,
      password: credentials.password,
    });
    if (!result.success || !result.data) {
      setError(Object.values(result.fieldErrors).join(' '));
      const field = formHost.current?.querySelector<HTMLInputElement>(
        result.firstField === 'password' ? '[name=password]' : '[name=username]',
      );
      field?.setAttribute('aria-invalid', 'true');
      field?.focus();
      return;
    }
    try {
      const user = await authApi(apiClient).login(result.data);
      if (!user.roles.some((role) => ADMIN_ROLES.has(role))) {
        setError('관리자 권한이 없는 계정입니다.');
        await authApi(apiClient)
          .logout()
          .catch(() => undefined);
        queryClient.clear();
        return;
      }
      queryClient.clear();
      router.push('/admin');
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.code === 'AUTH_INVALID_CREDENTIALS'
            ? '이메일 또는 비밀번호가 올바르지 않습니다.'
            : err.code === 'EMAIL_NOT_VERIFIED'
              ? '이메일 인증이 필요합니다.'
              : err.message
          : '로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
      );
    }
  }
  return (
    <div
      ref={formHost}
      className="flex min-h-dvh items-center justify-center px-4"
      data-testid="admin-login"
    >
      <LoginForm
        brand="Pinvi Admin"
        usernameLabel="이메일"
        description="관리자/운영자/CPO 계정으로 로그인하세요."
        onSubmit={submit}
        error={error}
        onClearError={clearError}
        testId="admin-login-form"
      />
    </div>
  );
}
