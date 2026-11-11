'use client';

import { useRef, type RefObject } from 'react';
import { isRestorableFocusTarget } from './focusTarget';

/** Radix 생명주기에 초기 대상/비활성 트리거 폴백만 연결한다. trap/stack/격리/scroll은 소유하지 않는다. */
export function useDialogFocus(
  initialFocusRef?: RefObject<HTMLElement | null>,
  returnFocusRef?: RefObject<HTMLElement | null>,
) {
  const contentRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  return {
    contentRef,
    onOpenAutoFocus(event: Event) {
      event.preventDefault();
      openerRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const panel = contentRef.current;
      const initial = initialFocusRef?.current;
      if (initial && panel?.contains(initial)) initial.focus({ preventScroll: true });
      if (panel && !panel.contains(document.activeElement)) panel.focus({ preventScroll: true });
    },
    onCloseAutoFocus(event: Event) {
      // controlled 호출부에는 Radix Trigger가 없을 수 있다. 재활성화되는 실제 opener를 우선한다.
      const restore = () => {
        const target = isRestorableFocusTarget(openerRef.current)
          ? openerRef.current
          : returnFocusRef?.current;
        if (!isRestorableFocusTarget(target)) return false;
        target.focus({ preventScroll: true });
        return true;
      };
      if (restore()) {
        event.preventDefault();
        return;
      }
      if (!openerRef.current && !returnFocusRef) return;
      // busy 해제/삭제 후 폴백 mount는 같은 React commit 다음 프레임에 안정화될 수 있다.
      let frames = 8;
      const retry = () => {
        if (!restore() && --frames > 0) requestAnimationFrame(retry);
      };
      requestAnimationFrame(retry);
    },
  };
}
