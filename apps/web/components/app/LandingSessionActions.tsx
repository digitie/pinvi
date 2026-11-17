'use client';

import { ButtonLink } from '@/components/ui/Button';
import { useEffect, useState } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801';

/**
 * 공개 랜딩(`/`) masthead 액션 — 로그인 사용자에게는 로그인·시작하기 대신 '내 홈'(/home)을 보인다.
 *
 * `apiClient`를 쓰지 않는다 — 401에 refresh를 시도하고 로그인 화면으로 보내는 동작은 익명 방문자에게
 * 맞지 않다. 세션 쿠키가 살아 있는지만 한 번 묻고, 아니면(401·네트워크 오류) 기본 액션을 둔다.
 */
export function LandingSessionActions() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    }).then(
      (response) => {
        if (!controller.signal.aborted) setSignedIn(response.ok);
      },
      () => {
        // 익명·오프라인 — 기본 액션 유지.
      },
    );
    return () => controller.abort();
  }, []);

  if (signedIn) {
    return (
      <ButtonLink href="/home" variant="secondary" data-testid="landing-my-home">
        내 홈
      </ButtonLink>
    );
  }
  return (
    <>
      <ButtonLink href="/login" variant="ghost">
        로그인
      </ButtonLink>
      <ButtonLink href="/signup" variant="secondary">
        시작하기
      </ButtonLink>
    </>
  );
}
