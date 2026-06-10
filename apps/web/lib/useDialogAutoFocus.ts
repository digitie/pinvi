import { useEffect, type RefObject } from 'react';

/**
 * 모달 다이얼로그의 포커스 관리.
 * - 열릴 때: `targetRef`(보통 첫 입력)로 포커스를 옮긴다 (WCAG 2.4.3).
 * - 닫힐 때: 다이얼로그를 열기 직전 포커스돼 있던 요소로 복원한다.
 *
 * paint 이후에 포커스해야 요소가 마운트된 상태이므로 rAF로 지연한다.
 */
export function useDialogAutoFocus(targetRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const raf = window.requestAnimationFrame(() => {
      targetRef.current?.focus();
    });
    return () => {
      window.cancelAnimationFrame(raf);
      // 복원 대상이 아직 문서에 있고 포커스 가능하면 되돌린다.
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
  }, [targetRef]);
}
