'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { FullPageMessage } from '@/components/feedback/FullPageMessage';
import { errorDigest, friendlyErrorText } from '@/lib/errorMessage';

export interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
  /** 로깅 출처 구분용 라벨 */
  scope?: string;
  testId?: string;
}

/**
 * App Router의 segment error boundary가 공통으로 쓰는 클라이언트 뷰.
 * 각 `error.tsx`는 이 컴포넌트를 얇게 감싸기만 한다.
 */
export function RouteError({ error, reset, scope = 'route', testId = 'route-error' }: RouteErrorProps) {
  useEffect(() => {
    console.error(`[tripmate] ${scope} error:`, error);
  }, [error, scope]);

  return (
    <FullPageMessage
      icon={AlertTriangle}
      title="문제가 발생했습니다"
      description={friendlyErrorText(error)}
      detail={errorDigest(error)}
      data-testid={testId}
    >
      <button
        type="button"
        onClick={reset}
        className="inline-flex items-center gap-2 rounded-sm bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-active"
        data-testid={`${testId}-retry`}
      >
        <RotateCcw className="h-4 w-4" aria-hidden="true" />
        다시 시도
      </button>
      <Link
        href="/"
        className="rounded-sm border border-hairline px-6 py-3 text-sm font-semibold text-ink hover:bg-surface-soft"
      >
        홈으로
      </Link>
    </FullPageMessage>
  );
}
