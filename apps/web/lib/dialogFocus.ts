'use client';

import { useEffect, useRef, type RefObject } from 'react';
import { isRestorableFocusTarget } from './focusTarget';

/** busy로 비활성화된 제출 버튼 대신 패널을 선택한다. 전역 focus trap은 Radix가 소유한다. */
export function useBusyDialogFocus(
  contentRef: RefObject<HTMLElement | null>,
  open: boolean,
  busy: boolean,
) {
  useEffect(() => {
    if (!open || !busy) return;
    const panel = contentRef.current;
    const active = document.activeElement;
    // 저장 버튼의 disabled 전환으로 포커스가 사라질 때만 유효한 도메인 대상을 유지한다.
    // 다른(중첩) 모달의 유효한 포커스는 공통 Radix가 소유한다.
    if (
      panel &&
      (active === document.body ||
        (active instanceof HTMLElement && panel.contains(active) && active.matches(':disabled')))
    ) {
      panel.focus({ preventScroll: true });
    }
  }, [busy, contentRef, open]);
}

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
