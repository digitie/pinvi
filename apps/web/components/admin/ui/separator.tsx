// kor-travel-map admin `src/components/ui/separator.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) `@base-ui/react/separator`의 `Separator` 제거. pinvi는 base-ui를 도입하지 않으므로
//      네이티브 `<div role="separator">`로 대체했다. base-ui가 하던 일은 (a) role/aria 부여,
//      (b) 방향 data 속성 부여 둘뿐이라 div로 완전히 대체된다.
//   2) 방향 variant — 원문의 `data-horizontal:` / `data-vertical:`는 KTM globals.css의
//      `@custom-variant`가 base-ui의 `data-horizontal`/`data-vertical` 속성에 맞춰 정의한 것이다.
//      pinvi에는 그 variant가 없으므로 표준 Tailwind 임의 variant
//      `data-[orientation=horizontal]:` / `data-[orientation=vertical]:`로 바꾸고, div에
//      `data-orientation`을 직접 붙여 선택자가 맞물리게 했다.
//   3) 색 토큰 치환 — `bg-border` -> `bg-admin-line`.
//   4) `'use client'` 제거. 원문에 있던 이유는 base-ui 클라이언트 프리미티브를 쓰기 때문이며,
//      순수 div가 된 지금은 서버 컴포넌트에서도 그대로 렌더된다.
// 크기·정렬 클래스(`shrink-0`, `h-px`, `w-full`, `w-px`, `self-stretch`)는 원문 그대로다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { cn } from '@/lib/admin/cn';

export interface SeparatorProps extends React.ComponentProps<'div'> {
  orientation?: 'horizontal' | 'vertical';
}

/** hairline rule — 섹션·툴바 사이의 유일한 구분선(`--color-admin-line`). */
function Separator({ className, orientation = 'horizontal', ...props }: SeparatorProps) {
  return (
    <div
      data-slot="separator"
      data-orientation={orientation}
      role="separator"
      aria-orientation={orientation}
      className={cn(
        'shrink-0 bg-admin-line data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:w-px data-[orientation=vertical]:self-stretch',
        className,
      )}
      {...props}
    />
  );
}

export { Separator };
