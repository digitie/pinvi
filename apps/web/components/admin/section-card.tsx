// kor-travel-map admin `src/components/section-card.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/components/ui/card` -> `@/components/admin/ui/card`,
//      `@/lib/utils` -> `@/lib/admin/cn` (pinvi admin 네임스페이스).
//   2) 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM design.md 전용 표식.
//   3) 문자열 따옴표만 pinvi prettier 설정(singleQuote)에 맞췄다.
// className 문자열(`space-y-4`, `border-b`)에는 색 토큰이 하나도 없어 치환표 적용 대상이 없었다.
// 구조·props·기본값(`size='sm'`, `headingLevel=2`)·헤더 hairline 구성은 원문 그대로다.

import * as React from 'react';

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/admin/ui/card';
import { cn } from '@/lib/admin/cn';

type SectionCardProps = {
  title: React.ReactNode;
  /** 제목 아래 한 문장 보조 설명(불필요하면 생략). */
  description?: React.ReactNode;
  /** 헤더 우측 액션 영역(새로고침 버튼 등) — primary ≤ 1. */
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'default' | 'sm';
  /** 제목의 heading level(기본 2). 페이지 안의 하위 패널이면 3. */
  headingLevel?: 2 | 3 | 4;
  className?: string;
  contentClassName?: string;
  children: React.ReactNode;
};

/**
 * 페이지 섹션의 유일한 컨테이너(design.md §Macrostructure — containment 1층).
 * 제목 행 + 아래 hairline(카드 폭 전체) + flat body. 이 안에 Card/bordered box를 다시 넣지 않는다:
 * 요약 dl은 DetailList, 선택 목록은 SelectableRow, 표는 DataTable(Card 안에서는 자동 flush).
 */
function SectionCard({
  title,
  description,
  actions,
  footer,
  size = 'sm',
  headingLevel = 2,
  className,
  contentClassName,
  children,
}: SectionCardProps) {
  return (
    <Card className={className} size={size}>
      <CardHeader className="border-b">
        <CardTitle aria-level={headingLevel}>{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
        {actions ? <CardAction>{actions}</CardAction> : null}
      </CardHeader>
      <CardContent className={cn('space-y-4', contentClassName)}>{children}</CardContent>
      {footer ? <CardFooter>{footer}</CardFooter> : null}
    </Card>
  );
}

export { SectionCard };
export type { SectionCardProps };
