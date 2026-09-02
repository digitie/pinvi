/**
 * 포커스 복원 대상 판별 — 모달 구현과 **무관한** 순수 DOM 술어(T-357).
 *
 * 원래 `lib/useModalDialog.ts`에 있었지만 그 모듈은 사용자 표면 모달 스택(focus trap · inert
 * 스냅샷)을 소유한다. admin은 base-ui가 그 역할을 하므로 admin 코드가 `useModalDialog`를
 * import하면 트랩이 두 벌이 될 수 있고, eslint 경계 가드가 그것을 막는다(T-356).
 *
 * 그런데 이 함수는 트랩이 아니라 "이 요소에 지금 포커스를 돌려줘도 되는가"만 본다 — 양쪽
 * 스택이 똑같이 필요로 하는 판별이다. 그래서 스택 밖으로 꺼내 공용으로 둔다. 복제하면 두
 * 구현이 갈라지고, 가드를 예외 처리하면 진짜 위반까지 함께 새어 나간다.
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
