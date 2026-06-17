import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export interface FullPageMessageProps {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  /** 참조용 짧은 코드(예: error digest) — 있으면 작게 표시 */
  detail?: string | null;
  /** 버튼·링크 등 액션 영역 */
  children?: ReactNode;
  'data-testid'?: string;
}

/**
 * 빈 상태 / 오류 / 404 등 한 화면을 채우는 안내 메시지의 공통 표현 컴포넌트.
 * 훅을 쓰지 않으므로 서버 컴포넌트(not-found)와 클라이언트 컴포넌트(error)
 * 양쪽에서 재사용할 수 있다.
 */
export function FullPageMessage({
  icon: Icon,
  title,
  description,
  detail,
  children,
  'data-testid': testId,
}: FullPageMessageProps) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-16 text-center">
      <div
        className="flex w-full max-w-lg flex-col items-center gap-4 rounded-md border border-hairline bg-canvas p-6 shadow-card"
        data-testid={testId}
      >
        {Icon ? (
          <span className="flex size-14 items-center justify-center rounded-full bg-surface-soft">
            <Icon className="size-7 text-muted" aria-hidden="true" />
          </span>
        ) : null}
        <h1 className="text-[20px] font-bold leading-snug text-ink md:text-[24px]">{title}</h1>
        {description ? (
          <p className="max-w-md text-[14px] leading-normal text-muted">{description}</p>
        ) : null}
        {children ? (
          <div className="mt-2 flex flex-wrap items-center justify-center gap-3">{children}</div>
        ) : null}
        {detail ? (
          <p
            className="mt-2 font-mono text-xs text-muted/70"
            data-testid="full-page-message-detail"
          >
            ref: {detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}
