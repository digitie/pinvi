'use client';

// kor-travel-map admin `src/components/ui/tooltip.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn`.
//      `@base-ui/react/tooltip` import는 원문 그대로다(`@base-ui/react@1.7.0`).
//   2) 색 토큰만 치환. tooltip은 ink-on-paper 반전이라 배경/글자 두 축 모두 치환한다:
//        bg-text-primary -> bg-ink       (치환표의 `text-text-primary`->`text-ink`와 같은 역할축.
//                                         KTM은 잉크 색을 배경으로 쓴다.)
//        text-surface-page -> text-admin-page (치환표의 `bg-surface-page`->`bg-admin-page`와 같은
//                                         역할축. #ffffff on #222222 = 15.9:1.)
//        shadow-elevated -> shadow-card / duration-base -> duration-normal
//   3) 그 외 타이밍(800ms)·`text-2xs`·`rounded-control`·모션·`data-slot` 이름은 원문 그대로다.
//
// NOTE(reduced motion): `data-motion="crossfade"` 취급은 `dialog.tsx` 상단 NOTE와 같다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import { Tooltip as TooltipPrimitive } from '@base-ui/react/tooltip';

import { cn } from '@/lib/admin/cn';

/**
 * Tooltip timing (design.md §Microinteractions): hover는 800ms 뒤 열려 포인터가 스쳐 지나갈 때
 * 툴팁이 번쩍이지 않는다. 키보드 포커스는 0ms(Base UI의 focus interaction은 `delay`를 읽지 않고
 * hover 경로만 읽는다). 팝업은 hover 가능하고(WCAG 1.4.13) Escape로 닫힌다. 한 화면의 툴팁은
 * Provider 하나로 감싸 인접 툴팁이 지연을 건너뛰게 한다.
 */
function TooltipProvider({ delay = 800, ...props }: TooltipPrimitive.Provider.Props) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" delay={delay} {...props} />;
}

function Tooltip({ ...props }: TooltipPrimitive.Root.Props) {
  return <TooltipPrimitive.Root data-slot="tooltip" {...props} />;
}

function TooltipTrigger({ ...props }: TooltipPrimitive.Trigger.Props) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

/**
 * Ink-on-paper 반전(`bg-ink` / `text-admin-page`)이라 tip이 패널이 아니라 라벨로 읽힌다.
 * Motion = opacity만, in `duration-normal` / out `duration-fast`; `data-instant`(focus / 그룹
 * hover / dismiss)는 transition 없이 렌더한다.
 */
function TooltipContent({
  className,
  sideOffset = 6,
  children,
  ...props
}: TooltipPrimitive.Popup.Props & { sideOffset?: number }) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner sideOffset={sideOffset} className="z-50">
        <TooltipPrimitive.Popup
          data-pv-surface="admin"
          data-slot="tooltip-content"
          data-motion="crossfade"
          className={cn(
            'max-w-xs rounded-control bg-ink px-3 py-1.5 text-2xs leading-normal text-admin-page shadow-card',
            'transition-opacity duration-normal ease-out data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 data-[ending-style]:duration-fast data-[ending-style]:ease-in data-[instant]:duration-0',
            className,
          )}
          {...props}
        >
          {children}
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
