import { Loader2 } from 'lucide-react';

export interface PageLoadingProps {
  label?: string;
  'data-testid'?: string;
}

/**
 * 라우트 전환 시 보여줄 전체 화면 로딩 표시. App Router의 `loading.tsx`에서
 * Suspense fallback으로 쓰인다. 훅이 없어 서버 컴포넌트로 동작한다.
 */
export function PageLoading({ label = '불러오는 중…', 'data-testid': testId }: PageLoadingProps) {
  return (
    <div
      className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4 py-16 text-center text-muted"
      role="status"
      aria-live="polite"
      data-testid={testId}
    >
      <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
