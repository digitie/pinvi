'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801';

/**
 * 공개 랜딩(`/`)에 로그인 사용자가 오면 개인 홈(`/home`)으로 보낸다.
 *
 * `apiClient`를 쓰지 않는다 — 401에 refresh를 시도하고 로그인 화면으로 보내는 동작은 익명 방문자에게
 * 맞지 않다. 세션 쿠키가 살아 있는지만 한 번 묻고, 아니면(401·네트워크 오류) 랜딩에 그대로 둔다.
 */
export function SignedInHomeRedirect() {
  const router = useRouter();
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    }).then(
      (response) => {
        if (response.ok && !controller.signal.aborted) router.replace('/home');
      },
      () => {
        // 익명·오프라인 — 랜딩 유지.
      },
    );
    return () => controller.abort();
  }, [router]);
  return null;
}
