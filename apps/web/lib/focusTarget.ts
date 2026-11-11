/**
 * 현재 렌더되고 활성화된 포커스 복원 대상의 순수 DOM 판별.
 * 공개·관리자 어댑터는 같은 common Radix 엔진을 사용하고 이 함수는 대상 선택만 돕는다.
 */
export function isRestorableFocusTarget(
  element: HTMLElement | null | undefined,
): element is HTMLElement {
  if (typeof document === 'undefined') return false;
  const computedStyle = element ? window.getComputedStyle(element) : null;
  return Boolean(
    element &&
    element !== document.body &&
    document.contains(element) &&
    !(element as HTMLElement & { disabled?: boolean }).disabled &&
    computedStyle?.display !== 'none' &&
    computedStyle?.visibility !== 'hidden' &&
    element.getClientRects().length > 0 &&
    // inert는 하위로 상속된다 — 자기 속성만 보면 배경 안 버튼을 "포커스 가능"으로 오판한다.
    element.closest('[inert]') === null,
  );
}
