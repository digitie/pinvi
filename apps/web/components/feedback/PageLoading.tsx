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
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-16 text-center">
      <div
        className="flex w-full max-w-sm flex-col items-center gap-3 rounded-md border border-hairline bg-canvas p-6 text-muted shadow-card"
        role="status"
        aria-live="polite"
        data-testid={testId}
      >
        <Loader2 className="size-6 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        <span className="text-[14px]">{label}</span>
      </div>
    </div>
  );
}
