// kor-travel-map admin `src/components/empty-state.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn` (pinvi admin 네임스페이스).
//   2) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        border-border -> border-admin-line / text-text-primary -> text-ink
//        text-text-tertiary -> text-muted / text-text-secondary -> text-body
// 레이아웃(좌측 정렬, `py-6`/`py-4` 밀도 분기, `max-w-prose`)·radius(`rounded-panel`)·타이포는
// 원문 그대로다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { cn } from '@/lib/admin/cn';

type EmptyStateProps = {
  /** 선택 — 제목 앞 16px 인라인 글리프(아이콘 타일 아님). */
  icon?: React.ReactNode;
  /** 무엇이 비었나 — 한 문장(`열린 이슈가 없습니다`). */
  title: string;
  /** 왜 / 다음 행동 안내 — 한 문장(`필터를 전체로 바꿔 보세요`). */
  description?: React.ReactNode;
  /** 다음 행동 하나(버튼/링크). */
  action?: React.ReactNode;
  /** 컨테이너가 없는 영역(빈 inspector rail 등)에서만 hairline 프레임을 켠다 — Card 안에서는 끈다(card-in-card 금지). */
  framed?: boolean;
  /** 밀도 — 테이블 안(sm)에서는 세로 여백을 줄인다. */
  size?: 'default' | 'sm';
  className?: string;
};

/**
 * 빈 상태 표준(design.md §Copy): 좌측 정렬, 한 문장 + 행동 하나. dashed border·가운데 정렬·
 * 아이콘-위-제목 타일을 쓰지 않는다(M17). DataTable은 `emptyState` prop으로 같은 컴포넌트를
 * table frame 안에 렌더한다.
 */
function EmptyState({
  icon,
  title,
  description,
  action,
  framed = false,
  size = 'default',
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-start gap-1 text-left',
        size === 'default' ? 'py-6' : 'py-4',
        framed && 'rounded-panel border border-admin-line px-4',
        className,
      )}
      data-slot="empty-state"
    >
      <div className="flex items-center gap-2 text-sm font-medium text-ink">
        {icon ? (
          <span aria-hidden="true" className="shrink-0 text-muted [&_svg]:size-4">
            {icon}
          </span>
        ) : null}
        <span>{title}</span>
      </div>
      {description ? <p className="max-w-prose text-xs text-body">{description}</p> : null}
      {action ? <div className="mt-2 flex flex-wrap items-center gap-2">{action}</div> : null}
    </div>
  );
}

export { EmptyState };
export type { EmptyStateProps };
