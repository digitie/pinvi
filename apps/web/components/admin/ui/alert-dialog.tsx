'use client';

// kor-travel-map admin `src/components/ui/alert-dialog.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/lib/utils` -> `@/lib/admin/cn`.
//      `@base-ui/react/alert-dialog` import는 원문 그대로다(`@base-ui/react@1.7.0`).
//   2) 색 토큰만 치환: bg-overlay -> bg-scrim/50 / bg-card -> bg-canvas /
//      border-border -> border-admin-line / text-text-primary -> text-ink /
//      text-text-secondary -> text-body / shadow-modal -> shadow-overlay /
//      duration-base -> duration-normal.
//   3) 그 외 레이아웃·간격·모션·`data-slot` 이름은 원문 그대로다.
//
// NOTE(reduced motion): `data-motion="crossfade"` 취급은 `dialog.tsx` 상단 NOTE와 같다.

// Hallmark · genre: editorial-utilitarian · macrostructure: Rail-Workbench · design-system: design.md · designed-as-app

import * as React from 'react';

import { AlertDialog as AlertDialogPrimitive } from '@base-ui/react/alert-dialog';

import { cn } from '@/lib/admin/cn';

/** `dialog.tsx`와 같은 overlay 레시피: scrim `bg-scrim/50`, 패널 opacity+scale .98. */
const ALERT_BACKDROP_CLASS =
  'fixed inset-0 z-50 bg-scrim/50 transition-opacity duration-normal ease-out data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 data-[ending-style]:duration-fast data-[ending-style]:ease-in';

const ALERT_POPUP_MOTION_CLASS =
  'transition-[opacity,scale] duration-normal ease-out data-[starting-style]:scale-98 data-[starting-style]:opacity-0 data-[ending-style]:scale-98 data-[ending-style]:opacity-0 data-[ending-style]:duration-fast data-[ending-style]:ease-in';

function AlertDialog({ ...props }: AlertDialogPrimitive.Root.Props) {
  return <AlertDialogPrimitive.Root data-slot="alert-dialog" {...props} />;
}

function AlertDialogTrigger({ ...props }: AlertDialogPrimitive.Trigger.Props) {
  return <AlertDialogPrimitive.Trigger data-slot="alert-dialog-trigger" {...props} />;
}

/**
 * `focus-visible:outline-0` — dialog.tsx와 같은 이유: 패널은 `tabIndex=-1`로 프로그램적 포커스만
 * 받는 컨테이너라 페이지 폭 링을 그리면 안 된다. `outline-none`은 금지 — 폭만 0으로 두는
 * `outline-0`이라야 `--tw-outline-style` 오염 없이 자식 컨트롤의 링이 살아 있다.
 */
function AlertDialogContent({ className, children, ...props }: AlertDialogPrimitive.Popup.Props) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Backdrop
        data-slot="alert-dialog-backdrop"
        className={ALERT_BACKDROP_CLASS}
      />
      <AlertDialogPrimitive.Viewport
        data-slot="alert-dialog-viewport"
        className="fixed inset-0 z-50 flex items-center justify-center overflow-auto p-4"
      >
        <AlertDialogPrimitive.Popup
          data-slot="alert-dialog-content"
          data-motion="crossfade"
          className={cn(
            'w-full max-w-md rounded-panel border border-admin-line bg-canvas p-5 text-ink shadow-overlay focus-visible:outline-0',
            ALERT_POPUP_MOTION_CLASS,
            className,
          )}
          {...props}
        >
          {children}
        </AlertDialogPrimitive.Popup>
      </AlertDialogPrimitive.Viewport>
    </AlertDialogPrimitive.Portal>
  );
}

function AlertDialogTitle({ className, ...props }: AlertDialogPrimitive.Title.Props) {
  return (
    <AlertDialogPrimitive.Title
      data-slot="alert-dialog-title"
      className={cn('text-md font-semibold text-ink', className)}
      {...props}
    />
  );
}

function AlertDialogDescription({ className, ...props }: AlertDialogPrimitive.Description.Props) {
  return (
    <AlertDialogPrimitive.Description
      data-slot="alert-dialog-description"
      className={cn('mt-2 text-sm text-body', className)}
      {...props}
    />
  );
}

function AlertDialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="alert-dialog-footer"
      className={cn('mt-5 flex flex-wrap items-center justify-end gap-2', className)}
      {...props}
    />
  );
}

function AlertDialogClose({ ...props }: AlertDialogPrimitive.Close.Props) {
  return <AlertDialogPrimitive.Close data-slot="alert-dialog-close" {...props} />;
}

export {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogTrigger,
};
