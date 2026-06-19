'use client';

import { useEffect, useMemo } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { FullPageMessage } from '@/components/feedback/FullPageMessage';
import { DocumentNavLink } from '@/components/navigation/DocumentNavLink';
import {
  errorReloadStorageKey,
  isLikelyRecoverableNextRuntimeError,
} from '@/lib/error-recovery';
import { errorDigest, friendlyErrorText } from '@pinvi/domain';

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
 *
 * chunk/RSC/network 계열 런타임 오류는 같은 pathname에서 1회만 hard reload로 복구를
 * 시도하고(`lib/error-recovery`), 반복 실패하면 한국어 복구 패널을 보여 준다. (T-278 이식)
 */
export function RouteError({
  error,
  reset,
  scope = 'route',
  testId = 'route-error',
}: RouteErrorProps) {
  const recoverable = useMemo(() => isLikelyRecoverableNextRuntimeError(error), [error]);

  useEffect(() => {
    console.error(`[pinvi] ${scope} error:`, error);
  }, [error, scope]);

  useEffect(() => {
    if (!recoverable || typeof window === 'undefined') return;
    const key = errorReloadStorageKey(window.location.pathname);
    if (window.sessionStorage.getItem(key) === '1') return;
    window.sessionStorage.setItem(key, '1');
    window.location.reload();
  }, [recoverable]);

  const retry = () => {
    if (typeof window !== 'undefined') {
      window.sessionStorage.removeItem(errorReloadStorageKey(window.location.pathname));
    }
    reset();
  };

  return (
    <FullPageMessage
      icon={AlertTriangle}
      title="문제가 발생했습니다"
      description={
        recoverable
          ? '현재 화면의 런타임 상태가 서버와 맞지 않아 새로고침이 필요합니다.'
          : friendlyErrorText(error)
      }
      detail={errorDigest(error)}
      data-testid={testId}
    >
      <button
        type="button"
        onClick={retry}
        className="focus-ring inline-flex min-h-11 items-center gap-2 rounded-sm bg-primary px-6 py-3 text-sm font-semibold text-white transition duration-fast ease-pinvi hover:bg-primary-active"
        data-testid={`${testId}-retry`}
      >
        <RotateCcw className="size-4" aria-hidden="true" />
        다시 시도
      </button>
      <DocumentNavLink
        href="/"
        className="focus-ring inline-flex min-h-11 items-center rounded-sm border border-hairline px-6 py-3 text-sm font-semibold text-ink transition duration-fast ease-pinvi hover:bg-surface-soft"
      >
        홈으로
      </DocumentNavLink>
    </FullPageMessage>
  );
}
