'use client';

import { useEffect } from 'react';

/**
 * 루트 레이아웃 자체가 깨졌을 때의 최후 방어선. 이 컴포넌트는 root layout을
 * 대체하므로 자체 <html>/<body>를 렌더링해야 하고, Tailwind/globals.css가
 * 로드되지 않은 상황도 가정해 인라인 스타일만 사용한다.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[pinvi] global error:', error);
  }, [error]);

  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          padding: 24,
          textAlign: 'center',
          fontFamily: 'Pretendard, "Apple SD Gothic Neo", system-ui, sans-serif',
          color: '#222222',
          backgroundColor: '#ffffff',
        }}
      >
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>문제가 발생했습니다</h1>
        <p style={{ maxWidth: 420, fontSize: 14, color: '#6a6a6a', margin: 0 }}>
          앱을 표시하는 중 심각한 오류가 발생했습니다. 다시 시도해 주세요.
        </p>
        <button
          type="button"
          onClick={reset}
          style={{
            cursor: 'pointer',
            borderRadius: 4,
            border: 'none',
            backgroundColor: '#ff385c',
            color: '#ffffff',
            padding: '12px 24px',
            fontSize: 14,
            fontWeight: 600,
          }}
          data-testid="global-error-retry"
        >
          다시 시도
        </button>
        {error.digest ? (
          <p style={{ fontFamily: 'monospace', fontSize: 12, color: '#9a9a9a', margin: 0 }}>
            ref: {error.digest}
          </p>
        ) : null}
      </body>
    </html>
  );
}
