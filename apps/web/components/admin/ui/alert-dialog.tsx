'use client';

import { AlertDialogContent as CommonContent } from '@kor-travel/ui/alert-dialog';
import type { ComponentProps, RefObject } from 'react';
export {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@kor-travel/ui/alert-dialog';

/** 기존 초기/복귀 포커스를 Radix 이벤트에 연결한다. */
export function AlertDialogContent({
  initialFocus,
  finalFocus,
  onOpenAutoFocus,
  onCloseAutoFocus,
  ...props
}: ComponentProps<typeof CommonContent> & {
  initialFocus?: RefObject<HTMLElement | null>;
  finalFocus?: RefObject<HTMLElement | null>;
}) {
  return (
    <CommonContent
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
    />
  );
}
