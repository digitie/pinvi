'use client';

import { AlertDialogContent as CommonContent } from '@kor-travel/ui/alert-dialog';
import { useRef, type ComponentProps, type RefObject } from 'react';
import { isRestorableFocusTarget } from '@/lib/focusTarget';
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
  const openerRef = useRef<HTMLElement | null>(null);
  return (
    <CommonContent
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
        const target = isRestorableFocusTarget(finalFocus?.current)
          ? finalFocus.current
          : openerRef.current;
        if (isRestorableFocusTarget(target)) {
          event.preventDefault();
          target.focus({ preventScroll: true });
        }
      }}
    />
  );
}
