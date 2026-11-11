'use client';

import {
  Dialog as CommonDialog,
  DialogContent as CommonDialogContent,
} from '@kor-travel/ui/dialog';
import * as React from 'react';
import { isRestorableFocusTarget } from '@/lib/focusTarget';
export {
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@kor-travel/ui/dialog';

const UnsavedInputContext = React.createContext(false);
export type DialogProps = React.ComponentProps<typeof CommonDialog> & { hasUnsavedInput?: boolean };

/** 입력이 있는 관리자 폼은 명시적 닫기만 허용한다. */
export function Dialog({ hasUnsavedInput = false, children, ...props }: DialogProps) {
  return (
    <UnsavedInputContext.Provider value={hasUnsavedInput}>
      <CommonDialog {...props}>{children}</CommonDialog>
    </UnsavedInputContext.Provider>
  );
}

type FocusTarget = React.RefObject<HTMLElement | null>;
type DialogContentProps = React.ComponentProps<typeof CommonDialogContent> & {
  initialFocus?: FocusTarget;
  finalFocus?: FocusTarget;
};
export function DialogContent({
  initialFocus,
  finalFocus,
  onOpenAutoFocus,
  onCloseAutoFocus,
  onEscapeKeyDown,
  onPointerDownOutside,
  ...props
}: DialogContentProps) {
  const unsaved = React.useContext(UnsavedInputContext);
  const openerRef = React.useRef<HTMLElement | null>(null);
  return (
    <CommonDialogContent
      showCloseButton={false}
      {...props}
      data-pv-surface="admin"
      onOpenAutoFocus={(event) => {
        openerRef.current =
          document.activeElement instanceof HTMLElement ? document.activeElement : null;
        onOpenAutoFocus?.(event);
        if (!event.defaultPrevented && initialFocus?.current) {
          event.preventDefault();
          initialFocus.current.focus();
        }
      }}
      onCloseAutoFocus={(event) => {
        onCloseAutoFocus?.(event);
        if (event.defaultPrevented) return;
        // 조건부 마운트 호출부는 DialogTrigger가 없어도 실제 열기 버튼으로 복귀한다.
        const target = isRestorableFocusTarget(finalFocus?.current)
          ? finalFocus.current
          : openerRef.current;
        if (isRestorableFocusTarget(target)) {
          event.preventDefault();
          target.focus({ preventScroll: true });
        }
      }}
      onEscapeKeyDown={(event) => {
        if (unsaved) event.preventDefault();
        onEscapeKeyDown?.(event);
      }}
      onPointerDownOutside={(event) => {
        if (unsaved) event.preventDefault();
        onPointerDownOutside?.(event);
      }}
    />
  );
}
