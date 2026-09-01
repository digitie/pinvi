'use client';
// kor-travel-map admin `src/components/ui/table.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn` (pinvi admin 네임스페이스).
//   2) 색 토큰만 pinvi 팔레트 이름으로 치환. 사용자 요구가 "색상톤 제외 일치"라 색 외에는
//      건드리지 않는다:
//        bg-card -> bg-canvas / bg-surface-subtle -> bg-admin-subtle
//        border-border -> border-admin-line / bg-brand-tint -> bg-error-bg
//        text-text-primary -> text-ink / text-text-secondary -> text-body
//   3) `[&_tr]:border-b`에 `[&_tr]:border-admin-line`을 덧붙였다. KTM globals.css는
//      `@layer base { * { @apply border-border } }`로 모든 요소의 기본 테두리 색을 hairline으로
//      깔아 두는데 pinvi에는 그 base 규칙이 없다. Tailwind v4의 기본 border-color는
//      `currentColor`라 그대로 두면 헤더 밑줄이 본문 잉크색으로 진하게 그려진다. 즉 이것도
//      "원문이 암묵적으로 지정하던 색 토큰"을 명시로 옮긴 것이지 새 스타일이 아니다.
// 레이아웃·간격·radius(`rounded-panel`)·높이(`h-9`)·타이포(`text-2xs`)·모션 클래스는 원문 그대로다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { cn } from '@/lib/admin/cn';

/**
 * Table — dense list의 기본 표면. 컨테이너는 Table 자신의 hairline(`rounded-panel border-admin-line`)
 * 하나뿐이다: 바깥에 다른 bordered box를 두지 않는다(C3). Card/SectionCard *안*에 놓이면
 * 자동으로 flush(테두리·모서리·배경 제거)가 되어 containment이 1층으로 유지된다.
 * 숫자 정렬을 위해 table 전체가 `tabular-nums`(M24), 헤더는 12px/600 secondary
 * (uppercase·tracking 없음, m3). 긴 본문 셀(message 등)은 `whitespace-normal`을 주어
 * clamp/wrap이 동작하게 한다(M38).
 */
function Table({
  className,
  containerClassName,
  containerStyle,
  containerTestId,
  ...props
}: React.ComponentProps<'table'> & {
  /** 스크롤 컨테이너(div) className — 높이 제한/스크롤 축 조정용. */
  containerClassName?: string;
  /** 스크롤 컨테이너(div) inline style. pinvi 추가(T-356) — 높이 제한이 런타임 값으로
   *  오는 호출부가 있다(AdminTable의 maxHeight prop). Tailwind는 실행 시점에 조립된 임의 값
   *  클래스를 정적 추출하지 못해 CSS가 아예 생성되지 않으므로 그런 치수는 style로 준다. */
  containerStyle?: React.CSSProperties;
  /** 스크롤 컨테이너(div)의 data-testid. pinvi 추가(T-356) — 기존 e2e가
   *  `admin-table-scroll`을 **실제로 스크롤한다**(`el.scrollTo(0, el.scrollHeight)`,
   *  `e2e/admin-table.e2e.ts`). 바깥 래퍼에 testid를 달면 그 호출이 스크롤 불가 요소에
   *  걸려 조용히 no-op이 되므로, 진짜 스크롤 컨테이너인 이 div가 testid를 가져야 한다. */
  containerTestId?: string;
}) {
  return (
    <div
      data-slot="table-container"
      data-testid={containerTestId}
      style={containerStyle}
      className={cn(
        'relative w-full overflow-x-auto rounded-panel border border-admin-line bg-canvas group-data-[slot=card]/card:rounded-none group-data-[slot=card]/card:border-0 group-data-[slot=card]/card:bg-transparent',
        containerClassName,
      )}
    >
      <table
        data-slot="table"
        className={cn('w-full caption-bottom text-sm tabular-nums', className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<'thead'>) {
  return (
    <thead
      data-slot="table-header"
      className={cn('bg-admin-subtle [&_tr]:border-b [&_tr]:border-admin-line', className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<'tbody'>) {
  return (
    <tbody
      data-slot="table-body"
      className={cn('[&_tr:last-child]:border-0', className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<'tfoot'>) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        'border-t border-admin-line bg-admin-subtle font-medium [&>tr]:last:border-b-0',
        className,
      )}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<'tr'>) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        // 전환 속성은 열거한다: v4 `transition-colors`는 `outline-color`까지 포함해
        // 클릭 가능한 행(`tabIndex=0`)의 포커스 링이 100ms 페이드인 된다(design.md §Focus).
        'border-b border-admin-line transition-[color,background-color,border-color] hover:bg-admin-subtle has-aria-expanded:bg-admin-subtle data-[state=selected]:bg-error-bg',
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<'th'>) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        'h-9 px-3 text-left align-middle text-2xs leading-none font-semibold whitespace-nowrap text-body [&:has([role=checkbox])]:pr-0',
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<'td'>) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        'px-3 py-2 align-middle whitespace-nowrap text-ink [&:has([role=checkbox])]:pr-0',
        className,
      )}
      {...props}
    />
  );
}

function TableCaption({ className, ...props }: React.ComponentProps<'caption'>) {
  return (
    <caption
      data-slot="table-caption"
      className={cn('mt-3 text-xs text-body', className)}
      {...props}
    />
  );
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
