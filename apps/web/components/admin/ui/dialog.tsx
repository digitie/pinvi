'use client';

import {
  Dialog as CommonDialog,
  DialogContent as CommonDialogContent,
} from '@kor-travel/ui/dialog';
import * as React from 'react';
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
  return (
    <CommonDialogContent
      showCloseButton={false}
      {...props}
      data-pv-surface="admin"
      onOpenAutoFocus={(event) => {
        onOpenAutoFocus?.(event);
        if (!event.defaultPrevented && initialFocus?.current) {
          event.preventDefault();
          initialFocus.current.focus();
        }
      }}
      onCloseAutoFocus={(event) => {
        onCloseAutoFocus?.(event);
        if (!event.defaultPrevented && finalFocus?.current) {
          event.preventDefault();
          finalFocus.current.focus();
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
