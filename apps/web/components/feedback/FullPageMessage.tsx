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
 *
 * DESIGN.md "Hallmark 잠금 시스템": 중앙 정렬 카드 + 원형 아이콘(AI empty-state 템플릿) 대신
 * 좌정렬 flat 문단 — 제목 위 hairline rule, 아이콘은 제목 옆 인라인, 그림자·카드 없음.
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
    <div className="mx-auto flex min-h-[60dvh] w-full max-w-6xl items-center px-6 py-16">
      <div className="w-full max-w-lg border-t-2 border-ink pt-6" data-testid={testId}>
        <h1 className="flex items-start gap-3 text-2xl font-bold leading-snug tracking-tight text-ink [overflow-wrap:anywhere]">
          {Icon ? <Icon className="mt-1 size-6 shrink-0 text-muted" aria-hidden="true" /> : null}
          <span>{title}</span>
        </h1>
        {description ? (
          <p className="mt-3 max-w-[46ch] text-base leading-relaxed text-body">{description}</p>
        ) : null}
        {children ? <div className="mt-6 flex flex-wrap items-center gap-3">{children}</div> : null}
        {detail ? (
          <p className="mt-6 font-mono text-xs text-muted" data-testid="full-page-message-detail">
            ref: {detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}
