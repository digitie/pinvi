// kor-travel-map admin `src/components/ui/skeleton.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn` (pinvi admin 네임스페이스).
//   2) 색 토큰만 치환 — `bg-surface-muted` -> `bg-admin-muted`.
//   3) `import * as React from 'react'`를 추가했다. 원문은 import 없이 `React.ComponentProps`를
//      쓰는데, 그건 전역 `React` 네임스페이스 타입에 기대는 형태다. pinvi web은 `jsx: preserve`
//      + React 19 타입이라 전역 네임스페이스를 보장하지 않아 명시 import가 필요하다(타입 전용
//      변경이며 런타임/클래스에는 영향이 없다).
// `animate-pulse`·`rounded-control`·`motion-reduce:animate-none`은 원문 그대로다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { cn } from '@/lib/admin/cn';

/**
 * Skeleton — 대체할 콘텐츠의 형태를 그대로 따라 그린다(텍스트 줄 = h-4, 숫자 = h-8 w-24 …).
 * 장식 요소라 기본 aria-hidden; 로딩 여부는 감싸는 영역의 `aria-busy`가 알린다.
 * pulse는 전역 reduced-motion 규칙(app/globals.css)이 끈다.
 */
function Skeleton({
  className,
  'aria-hidden': ariaHidden = true,
  ...props
}: React.ComponentProps<'div'>) {
  return (
    <div
      aria-hidden={ariaHidden}
      data-slot="skeleton"
      className={cn(
        'animate-pulse rounded-control bg-admin-muted motion-reduce:animate-none',
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
