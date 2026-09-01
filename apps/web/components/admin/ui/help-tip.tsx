'use client';

// kor-travel-map admin `src/components/help-tip.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/components/ui/popover` -> `@/components/admin/ui/popover`,
//      `@/components/ui/tooltip` -> `@/components/admin/ui/tooltip`,
//      `@/lib/utils` -> `@/lib/admin/cn`.
//   2) 색 토큰만 치환: `text-text-secondary`->`text-body`, `bg-surface-subtle`->`bg-admin-subtle`,
//      `text-text-primary`->`text-ink`, `bg-surface-muted`->`bg-admin-muted`,
//      `text-text-disabled`->`text-muted-soft`.
//   3) 배선(Popover open state / Tooltip render 합성 / `align="start"` /
//      `className="leading-relaxed"`)과 `aria-label`·문구는 원문 그대로다.
//
// 이력: 이 파일의 이전 판은 pinvi에 `@base-ui/react`가 없다는 전제로 hover 툴팁을 네이티브
// `title` 속성으로, 클릭 팝오버를 로컬 state + 절대배치 `<div role="dialog">`로 대체했었다.
// 그 판은 스스로 "포커스 관리가 없다"를 한계로 적어 뒀다(Portal/Positioner 없음, focus 이동 없음,
// children이 문자열이 아니면 hover 미리보기 소멸). `@base-ui/react@1.7.0`이 설치되면서 그 우회를
// 전부 걷어내고 KTM 원문 구조(Popover + Tooltip 프리미티브)로 되돌렸다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';
import { CircleHelpIcon } from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/admin/ui/popover';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/admin/ui/tooltip';
import { cn } from '@/lib/admin/cn';

type HelpTipProps = {
  /** 도움말 대상 필드/항목 이름 — 접근성 이름 `도움말: {label}`을 만든다. */
  label: string;
  children: React.ReactNode;
  className?: string;
};

/**
 * 필드 옆 도움말 아이콘 버튼.
 * hover(800ms) / focus(0ms) = Tooltip(빠른 훑기), click = Popover(터치 기기 안전 + 긴 내용).
 * 본문 상세 설명을 인라인 hint 대신 여기로 옮긴다.
 *
 * Hit target: 24px 시각 박스 + `before:` 의사요소로 포인터 타깃을 40px까지 확장한다(14px 글리프와
 * 인라인 레이아웃은 그대로). 상태: rest ink-2 · hover/open ink on paper-2 · active paper-3 ·
 * focus는 outline recipe 1종.
 */
function HelpTip({ label, children, className }: HelpTipProps) {
  const [popoverOpen, setPopoverOpen] = React.useState(false);

  const trigger = (
    <button
      aria-label={`도움말: ${label}`}
      className={cn(
        'relative inline-flex size-6 shrink-0 items-center justify-center rounded-control text-body transition-[color,background-color] duration-fast ease-out',
        'before:absolute before:-inset-2',
        'hover:bg-admin-subtle hover:text-ink active:bg-admin-muted aria-expanded:bg-admin-subtle aria-expanded:text-ink',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        'disabled:pointer-events-none disabled:text-muted-soft',
        className,
      )}
      type="button"
    >
      <CircleHelpIcon aria-hidden className="size-3.5" />
    </button>
  );

  return (
    <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger render={<PopoverTrigger render={trigger} />} />
          {popoverOpen ? null : <TooltipContent>{children}</TooltipContent>}
        </Tooltip>
      </TooltipProvider>
      <PopoverContent align="start" className="leading-relaxed">
        {children}
      </PopoverContent>
    </Popover>
  );
}

export { HelpTip };
export type { HelpTipProps };
