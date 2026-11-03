'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ApiError, authApi } from '@pinvi/api-client';
import { apiClient } from '@/lib/api';

/** 서버 세션을 종료한 뒤 인증 화면으로 이동한다. */
export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <div className="space-y-2">
    <button type="button" disabled={pending} className="focus-ring min-h-11 rounded-sm border border-hairline px-4 text-sm font-semibold"
      onClick={async () => {
        if (pending) return;
        setPending(true); setError(null);
        try {
          await authApi(apiClient).logout();
          router.replace('/login');
          router.refresh();
        } catch (err) {
          setError(err instanceof ApiError ? err.message : '로그아웃하지 못했습니다. 다시 시도해 주세요.');
          setPending(false);
        }
      }}>{pending ? '로그아웃 중…' : '로그아웃'}</button>
    {error && <p role="alert" className="text-sm text-error-text">{error}</p>}
  </div>;
}
