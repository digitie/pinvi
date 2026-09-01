'use client';

// kor-travel-map admin `src/components/ui/dialog.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn` (pinvi admin 네임스페이스).
//      `@base-ui/react/dialog` import는 원문 그대로다 — pinvi에 `@base-ui/react@1.7.0`이 설치됐다.
//   2) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        bg-overlay -> bg-scrim/50 / bg-card -> bg-canvas / border-border -> border-admin-line
//        text-text-primary -> text-ink / text-text-secondary -> text-body
//        shadow-modal -> shadow-overlay / duration-base -> duration-normal
//      `ease-out`/`ease-in`/`duration-fast`/`z-50`/`scale-98`/`rounded-panel`/`text-md`는 pinvi에도
//      같은 이름으로 있어 그대로 둔다.
//   3) `DialogContent`에 `viewportProps` 하나를 더했다(원문에는 없음). pinvi e2e는 scrim 클릭
//      닫힘을 `admin-integrity-action-overlay` / `restore-hotswap-dialog-backdrop` testid로 잡는데,
//      Backdrop과 Viewport가 둘 다 `fixed inset-0 z-50`이고 Viewport가 DOM 뒤라 화면 가장자리에서
//      실제로 클릭을 받는 층은 **Viewport**다. testid를 Backdrop에 달면 Playwright hit-test가
//      Viewport에 가로막혀 클릭이 실패한다. className·레이아웃은 그대로 두고 pass-through만 열었다.
//   4) 그 외 레이아웃·간격·모션·`data-*` 속성·`data-slot` 이름은 원문 그대로다.
//
// NOTE(reduced motion): KTM globals.css는 `[data-motion="crossfade"]`에 "opacity만 150ms" 규칙을
// 따로 두지만, pinvi globals.css의 `prefers-reduced-motion` 블록은 모든 transition을 0.01ms로
// 죽인다(더 강한 축약). 속성 자체는 원문 마크업 보존 + 나중에 같은 규칙을 달 훅으로 남겨 둔다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { Dialog as DialogPrimitive } from '@base-ui/react/dialog';

import { cn } from '@/lib/admin/cn';

/**
 * Overlay motion recipe (design.md §Motion): enter = opacity + scale .98, `duration-normal`
 * `ease-out`; exit = `duration-fast` `ease-in`. Scrim은 유일한 alpha 색이다(`bg-scrim/50`).
 * `data-motion="crossfade"`는 reduced-motion 훅(위 NOTE 참고).
 */
const OVERLAY_BACKDROP_CLASS =
  'fixed inset-0 z-50 bg-scrim/50 transition-opacity duration-normal ease-out data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 data-[ending-style]:duration-fast data-[ending-style]:ease-in';

const OVERLAY_POPUP_MOTION_CLASS =
  'transition-[opacity,scale] duration-normal ease-out data-[starting-style]:scale-98 data-[starting-style]:opacity-0 data-[ending-style]:scale-98 data-[ending-style]:opacity-0 data-[ending-style]:duration-fast data-[ending-style]:ease-in';

function Dialog({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />;
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

/**
 * 화면 중앙(상단 정렬) 팝업. 스크롤은 backdrop(viewport) 영역에서. panel 표면은 다른
 * elevated surface와 같은 `bg-canvas` + hairline + `rounded-panel`, 그림자는 `shadow-overlay`만.
 *
 * `focus-visible:outline-0` — 패널은 `tabIndex=-1`로 **프로그램적 포커스만** 받는 컨테이너다
 * (열릴 때 base-ui가 여기로 포커스를 옮긴다). 키보드로 열면 base 레시피의 링이 다이얼로그
 * 전체를 두르는데, 조작 가능한 요소가 아니라 상태 변화는 패널 등장·scrim이 이미 알린다.
 * `outline-none`은 쓰지 않는다 — tailwind v4에서 `--tw-outline-style: none`이 요소의 outline
 * style 자체를 죽여 이후 어떤 focus-visible 선언으로도 링을 되살릴 수 없다.
 * `outline-0`은 폭만 0이라 style 오염이 없고, 패널 안의 컨트롤은 base 레시피의 링을 그대로 받는다.
 */
function DialogContent({
  className,
  children,
  viewportProps,
  ...props
}: DialogPrimitive.Popup.Props & {
  /**
   * pinvi 추가(원문에 없음) — scrim 층(Viewport)에 `data-testid` 같은 속성을 넘긴다.
   * 파일 상단 주석 ③ 참고. className은 넘기지 않는다(원문 레시피 고정).
   */
  viewportProps?: Omit<DialogPrimitive.Viewport.Props, 'className' | 'children'> & {
    'data-testid'?: string;
  };
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Backdrop data-slot="dialog-backdrop" className={OVERLAY_BACKDROP_CLASS} />
      <DialogPrimitive.Viewport
        data-slot="dialog-viewport"
        className="fixed inset-0 z-50 flex items-start justify-center overflow-auto p-4"
        {...viewportProps}
      >
        <DialogPrimitive.Popup
          data-slot="dialog-content"
          data-motion="crossfade"
          className={cn(
            'w-full max-w-lg rounded-panel border border-admin-line bg-canvas text-ink shadow-overlay focus-visible:outline-0',
            OVERLAY_POPUP_MOTION_CLASS,
            className,
          )}
          {...props}
        >
          {children}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Viewport>
    </DialogPrimitive.Portal>
  );
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="dialog-header"
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 border-b border-admin-line px-4 py-3',
        className,
      )}
      {...props}
    />
  );
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn('text-md font-semibold text-ink', className)}
      {...props}
    />
  );
}

function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn('text-sm text-body', className)}
      {...props}
    />
  );
}

function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        'flex flex-wrap items-center justify-end gap-2 border-t border-admin-line px-4 py-3',
        className,
      )}
      {...props}
    />
  );
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
};
