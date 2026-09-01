// kor-travel-map admin `src/components/ui/breadcrumb.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) **base-ui 제거** — 원문 `BreadcrumbLink`는 `@base-ui/react`의 `useRender` + `mergeProps`로
//      임의 엘리먼트(next/link 등) 렌더를 지원한다. pinvi에는 `@base-ui/react`가 없어
//      `React.cloneElement` 기반 최소 구현으로 대체했다. 외부 API(`render` prop, `<a>` 기본 태그,
//      `data-slot="breadcrumb-link"`)와 className 문자열은 그대로 유지된다.
//      병합 규칙: 기본 className이 먼저, 그 위에 호출부 className, 마지막으로 render 엘리먼트 자신의
//      className이 얹힌다(base-ui `mergeProps`의 우선순위와 같다). `children`은 render 엘리먼트가
//      직접 준 값이 있을 때만 그것을 쓰고, 없으면 호출부 children을 넘긴다 —
//      `{...render.props}`를 통째로 펼치면 `children: undefined`가 호출부 children을 지운다.
//   2) import 경로 — `@/lib/utils` -> `@/lib/admin/cn`.
//   3) 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM design.md 전용 표식.
//   4) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        text-text-secondary -> text-body / text-text-primary -> text-ink
//        text-text-tertiary -> text-muted (`outline-focus`는 pinvi에도 같은 이름이라 그대로)
//   5) 따옴표/세미콜론만 pinvi prettier 설정에 맞췄다.
// 레이아웃·gap·`rounded-control`·전환 속성 열거는 원문 그대로다.

import * as React from 'react';
import { ChevronRightIcon } from 'lucide-react';

import { cn } from '@/lib/admin/cn';

/**
 * Breadcrumb — 헤더 밴드의 위치 표기(13.5px secondary). 링크는 밑줄 없이 hover 시 잉크가
 * 짙어지고, 현재 페이지만 500 ink. `BreadcrumbLink`는 `render`로 next/link를 받을 수 있다.
 */
function Breadcrumb({ ...props }: React.ComponentProps<'nav'>) {
  return <nav aria-label="breadcrumb" data-slot="breadcrumb" {...props} />;
}

function BreadcrumbList({ className, ...props }: React.ComponentProps<'ol'>) {
  return (
    <ol
      data-slot="breadcrumb-list"
      className={cn('flex flex-wrap items-center gap-1.5 text-xs break-words text-body', className)}
      {...props}
    />
  );
}

function BreadcrumbItem({ className, ...props }: React.ComponentProps<'li'>) {
  return (
    <li
      data-slot="breadcrumb-item"
      className={cn('inline-flex items-center gap-1.5', className)}
      {...props}
    />
  );
}

type BreadcrumbLinkProps = React.ComponentProps<'a'> & {
  /** `<a>` 대신 렌더할 엘리먼트(예: `<Link href="/x" />`). base-ui `useRender`의 최소 대체. */
  render?: React.ReactElement<Record<string, unknown>>;
};

function BreadcrumbLink({ className, render, ...props }: BreadcrumbLinkProps) {
  const mergedClassName = cn(
    // 전환 속성 열거(v4 `transition-colors`는 `outline-color` 포함 → 포커스 링이 페이드인).
    'rounded-control no-underline transition-[color,background-color,border-color] hover:text-ink hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:text-ink',
    className,
  );
  if (render) {
    const renderProps = render.props;
    return React.cloneElement(render, {
      'data-slot': 'breadcrumb-link',
      ...props,
      ...renderProps,
      className: cn(mergedClassName, renderProps.className as string | undefined),
      children: renderProps.children ?? props.children,
    });
  }
  return <a className={mergedClassName} data-slot="breadcrumb-link" {...props} />;
}

function BreadcrumbPage({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      aria-current="page"
      data-slot="breadcrumb-page"
      className={cn('font-medium text-ink', className)}
      {...props}
    />
  );
}

function BreadcrumbSeparator({ children, className, ...props }: React.ComponentProps<'li'>) {
  return (
    <li
      aria-hidden="true"
      data-slot="breadcrumb-separator"
      role="presentation"
      className={cn('text-muted [&>svg]:size-3.5', className)}
      {...props}
    >
      {children ?? <ChevronRightIcon />}
    </li>
  );
}

export {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
};
export type { BreadcrumbLinkProps };
