'use client';

import {
  useEffect,
  useId,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from 'react';

/**
 * 모달 다이얼로그의 공통 a11y·상호작용을 한 곳에 모은다(TDR, ADR-056).
 *
 * 기존에는 `ConflictDialog` 등 각 다이얼로그가 focus 이동/Escape 처리를 제각기
 * inline으로 재구현했다. 이 훅은 다음을 한 번에 배선한다:
 * - 열릴 때 포커스를 패널(또는 `initialFocusRef`)로 이동, 닫힐 때 직전 요소로 복원(WCAG 2.4.3)
 * - Escape로 닫기(`event.stopPropagation`으로 바깥 핸들러와 충돌 방지)
 * - Tab 순환 focus-trap(모달 밖으로 포커스가 새지 않게)
 * - body 스크롤 잠금(중첩 모달까지 안전하도록 참조 카운트)
 * - backdrop 클릭 닫기(패널 안에서 드래그해 backdrop에서 놓아도 닫히지 않음)
 * - `role="dialog"` / `aria-modal` / `aria-label(ledby)` 배선
 *
 * 반환하는 `backdropProps`·`dialogProps`를 각각 backdrop/패널에 spread하면 된다.
 * `ariaLabel`을 주지 않으면 `aria-labelledby={titleId}`가 걸리므로 제목 요소에
 * `id={titleId}`를 달아야 한다.
 */
export interface UseModalDialogOptions {
  /** 모달을 닫는 콜백(Escape·backdrop 공통). 닫기 버튼도 이 콜백을 부르면 된다. */
  onClose: () => void;
  /** false면 리스너/스크롤 잠금을 걸지 않는다(패널을 조건부 렌더하는 대신 쓸 때). 기본 true. */
  active?: boolean;
  /** Escape로 닫기. 기본 true. */
  closeOnEscape?: boolean;
  /** backdrop 클릭으로 닫기. 기본 true. */
  closeOnBackdrop?: boolean;
  /** body 스크롤 잠금. 기본 true. */
  lockScroll?: boolean;
  /** 열릴 때 포커스를 옮길 대상. 생략하면 패널 자체로 이동한다. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /**
   * 닫힐 때 포커스를 돌려줄 대상(트리거 버튼). 직전 포커스 요소가 마운트 시점에 이미
   * disabled였거나(공유 busy 플래그) 사라진 경우의 폴백이다 — 없으면 포커스가 body에 남는다.
   */
  returnFocusRef?: RefObject<HTMLElement | null>;
  /** aria-label로 쓸 제목 텍스트. 주면 `aria-labelledby` 대신 이걸 쓴다. */
  ariaLabel?: string;
  /** aria-labelledby로 쓸 heading의 id. 생략하면 훅이 만든 `titleId`를 쓴다. */
  ariaLabelledBy?: string;
  /** aria-describedby로 쓸 설명 요소의 id. */
  ariaDescribedBy?: string;
  /**
   * body 직계 컨테이너로 portal할지. 기본 true.
   *
   * 배경 `inert`는 "모달이 inert 대상의 자손이 아닐 때"만 성립한다 — 앱 트리 안에서 뜨면
   * 앱 루트를 잠그는 순간 자기 자신까지 잠긴다. 그래서 portal이 격리의 선행 조건이다.
   */
  portal?: boolean;
  /**
   * 열려 있는 동안 배경을 `inert`로 만들지. 기본 true.
   * 스택 최상단 모달의 portal 컨테이너만 남기고 나머지 body 자식에 건다.
   */
  inertBackground?: boolean;
}

export interface ModalDialogA11y {
  /** 패널 요소 ref(`dialogProps.ref`와 동일 객체). focus-trap 대상. */
  dialogRef: RefObject<HTMLDivElement | null>;
  /**
   * portal 대상 컨테이너. `portal: false`거나 아직 마운트 전(SSR/첫 렌더)이면 null이다.
   * 훅은 렌더할 수 없으므로 `createPortal(node, portalContainer)` 호출은 호출부가 한다.
   */
  portalContainer: HTMLElement | null;
  /** 제목 요소에 달 id. `ariaLabel`을 주지 않았다면 이 id로 aria 연결된다. */
  titleId: string;
  /** backdrop(scrim) 요소에 spread. */
  backdropProps: {
    onMouseDown: (event: ReactMouseEvent) => void;
    onClick: (event: ReactMouseEvent) => void;
  };
  /** 패널 요소에 spread. */
  dialogProps: {
    ref: RefObject<HTMLDivElement | null>;
    tabIndex: number;
    role: 'dialog';
    'aria-modal': true;
    'aria-label'?: string;
    'aria-labelledby'?: string;
    'aria-describedby'?: string;
  };
}

// 여러 모달이 동시에 스크롤을 잠글 수 있으므로, 마지막 하나가 풀릴 때만 원복한다.
let scrollLockCount = 0;
let previousBodyOverflow: string | null = null;

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

// 중첩 모달에서 최상단 하나만 Escape/Tab에 반응하도록 활성 인스턴스를 쌓는다.
// (document 리스너는 stopPropagation으로 서로 막을 수 없으므로 최상단 가드가 필요.)
const modalStack: string[] = [];
// 닫히는 모달이 포커스를 아래 모달로 넘길 수 있도록 id→패널을 들고 있는다.
const modalPanels = new Map<string, HTMLElement>();
// id→portal 컨테이너. 배경 inert가 "최상단 모달만 남기고 잠그기" 위해 필요하다.
const modalContainers = new Map<string, HTMLElement>();
// inert를 요구하는 인스턴스 id 집합(모두 닫히면 원복).
const inertRequests = new Set<string>();
// 원래 inert 상태 스냅샷 — 인스턴스별로 뜨고 지면 중첩에서 깨지므로 전역 1개만 둔다.
let inertSnapshot: { element: HTMLElement; hadInert: boolean }[] | null = null;

/** 렌더되지 않거나 접근성 트리에 의미 없는 노드는 inert 대상에서 뺀다(쓰기 비용·부작용 감소). */
function isInertCandidate(element: Element): element is HTMLElement {
  if (!(element instanceof HTMLElement)) return false;
  const tag = element.tagName;
  if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK' || tag === 'TEMPLATE') return false;
  if (tag === 'META' || tag === 'NOSCRIPT') return false;
  // 라우트 변경 안내는 모달이 열려 있어도 살아 있어야 한다.
  if (tag === 'NEXT-ROUTE-ANNOUNCER') return false;
  return true;
}

function isRestorableFocusTarget(element: HTMLElement | null | undefined): element is HTMLElement {
  if (typeof document === 'undefined') return false;
  return Boolean(
    element &&
      element !== document.body &&
      document.contains(element) &&
      !(element as HTMLElement & { disabled?: boolean }).disabled &&
      // inert는 하위로 상속된다 — 자기 속성만 보면 배경 안 버튼을 "포커스 가능"으로 오판한다.
      element.closest('[inert]') === null,
  );
}

function focusWhenRestorable(resolveTarget: () => HTMLElement | null | undefined): void {
  if (typeof window === 'undefined') return;

  let remainingFrames = 8;
  const tryFocus = () => {
    const target = resolveTarget();
    if (isRestorableFocusTarget(target)) {
      target.focus({ preventScroll: true });
      return;
    }
    remainingFrames -= 1;
    if (remainingFrames > 0) window.requestAnimationFrame(tryFocus);
  };

  tryFocus();
}

/**
 * 배경 격리 동기화 — 최상단 모달의 컨테이너만 제외하고 body 자식에 `inert`를 건다.
 *
 * 인스턴스별 스냅샷/복원은 중첩에서 깨진다(아래 모달이 먼저 닫히며 배경 inert를 풀어 버린다).
 * 스택이 바뀔 때마다 최상단 기준으로 다시 계산하고, 원복은 마지막 요청이 사라질 때 한 번만 한다.
 *
 * `aria-hidden`은 걸지 않는다 — inert가 이미 접근성 트리에서 하위를 제거하고, focused 요소의
 * 조상에 aria-hidden을 거는 것은 ARIA 위반이다(DESIGN.md 모달 계약).
 */
function syncBackgroundInert(): void {
  if (typeof document === 'undefined') return;

  if (inertRequests.size === 0) {
    inertSnapshot?.forEach(({ element, hadInert }) => {
      if (hadInert) element.setAttribute('inert', '');
      else element.removeAttribute('inert');
    });
    inertSnapshot = null;
    return;
  }

  const topId = [...modalStack].reverse().find((id) => inertRequests.has(id));
  const keep = topId ? modalContainers.get(topId) : null;
  const candidates = Array.from(document.body.children).filter(isInertCandidate);

  if (inertSnapshot === null) {
    inertSnapshot = candidates.map((element) => ({
      element,
      hadInert: element.hasAttribute('inert'),
    }));
  }

  candidates.forEach((element) => {
    // 최상단 모달의 컨테이너(그리고 그 안의 모든 것)는 살아 있어야 한다.
    if (keep && (element === keep || element.contains(keep))) {
      const snapshot = inertSnapshot?.find((entry) => entry.element === element);
      if (!snapshot?.hadInert) element.removeAttribute('inert');
      return;
    }
    element.setAttribute('inert', '');
  });
}

export function useModalDialog(options: UseModalDialogOptions): ModalDialogA11y {
  const {
    onClose,
    active = true,
    closeOnEscape = true,
    closeOnBackdrop = true,
    lockScroll = true,
    initialFocusRef,
    returnFocusRef,
    ariaLabel,
    ariaLabelledBy,
    ariaDescribedBy,
    portal = true,
    inertBackground = true,
  } = options;

  const dialogRef = useRef<HTMLDivElement | null>(null);
  // 컨테이너는 **첫 렌더에 동기로** 만든다(append는 effect에서). 상태로 뒤늦게 만들면 패널이
  // 한 렌더 늦게 붙어, 초기 포커스 rAF가 아직 없는 패널을 잡으려다 no-op이 된다.
  const [portalNode] = useState<HTMLElement | null>(() =>
    typeof document === 'undefined' || !portal ? null : document.createElement('div'),
  );
  const generatedTitleId = useId();
  const titleId = ariaLabelledBy ?? generatedTitleId;
  // backdrop에서 pointer가 눌렸는지 추적(패널 안에서 시작한 드래그로는 닫지 않기 위해).
  const pointerDownOnBackdrop = useRef(false);

  // onClose가 매 렌더 새 참조로 와도 keydown effect를 재구독하지 않도록 최신값을 ref로 유지.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // initialFocusRef는 값이 아니라 ref로 읽는다 — 호출부가 상태에 따라 다른 ref를 넘겨도
  // (예: 완료 화면에서 닫기 버튼) focus effect가 재실행되며 cleanup이 포커스를 모달 밖으로
  // 되돌렸다 다시 들어오는 왕복이 생기지 않는다.
  const initialFocusRefRef = useRef(initialFocusRef);
  useEffect(() => {
    initialFocusRefRef.current = initialFocusRef;
  }, [initialFocusRef]);

  const returnFocusRefRef = useRef(returnFocusRef);
  useEffect(() => {
    returnFocusRefRef.current = returnFocusRef;
  }, [returnFocusRef]);

  // portal 컨테이너를 body 직계 자식으로 붙인다 — 배경 inert의 선행 조건이다.
  useEffect(() => {
    if (!active || !portalNode) return;
    portalNode.dataset.modalPortal = '';
    document.body.appendChild(portalNode);
    modalContainers.set(generatedTitleId, portalNode);
    syncBackgroundInert();
    return () => {
      modalContainers.delete(generatedTitleId);
      portalNode.remove();
      syncBackgroundInert();
    };
  }, [active, portalNode, generatedTitleId]);

  // ① opener 캡처 — **배경 inert보다 먼저**. inert가 걸리는 순간 브라우저가 그 안의 focused
  //    요소를 blur하므로, 뒤에서 캡처하면 복원 대상이 항상 body가 된다.
  const openerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!active) return;
    openerRef.current = (document.activeElement as HTMLElement | null) ?? null;
  }, [active]);

  // ② 배경 inert — cleanup(해제)이 ③의 포커스 복원보다 **먼저** 돌아야 한다.
  //    (React는 effect/cleanup을 선언 순서대로 실행한다.)
  useEffect(() => {
    if (!active || !inertBackground) return;
    inertRequests.add(generatedTitleId);
    syncBackgroundInert();
    return () => {
      inertRequests.delete(generatedTitleId);
      syncBackgroundInert();
    };
  }, [active, inertBackground, generatedTitleId]);

  // ③ 포커스: 열릴 때 패널/초기 대상으로, 닫힐 때 직전 요소로 복원.
  useEffect(() => {
    if (!active) return;
    const previouslyFocused = openerRef.current;
    // paint 이후 요소가 마운트된 상태에서 포커스하도록 rAF로 지연.
    const raf = window.requestAnimationFrame(() => {
      (initialFocusRefRef.current?.current ?? dialogRef.current)?.focus();
      // 초기 대상이 포커스 불가(예: busy로 disabled된 버튼)라 포커스가 안 들어갔으면
      // 패널로 폴백해 항상 다이얼로그 안에 포커스가 놓이게 한다(WCAG 2.4.3).
      const panel = dialogRef.current;
      if (panel && !panel.contains(document.activeElement)) {
        panel.focus();
      }
    });
    return () => {
      window.cancelAnimationFrame(raf);
      // previouslyFocused는 body이거나(트리거가 공유 busy로 이미 disabled된 채 열린 경우)
      // 이미 사라졌을 수 있다. 그러면 (1) 남아 있는 최상단 모달 → (2) 호출부가 준 트리거 순으로
      // 넘긴다. inert/portal cleanup은 React effect 순서와 브라우저 blur 타이밍에 따라 한두
      // 프레임 늦게 안정화될 수 있으므로, 실제 복원 가능 상태가 될 때까지 짧게 재시도한다.
      focusWhenRestorable(() => {
        if (isRestorableFocusTarget(previouslyFocused)) return previouslyFocused;
        const belowId = modalStack.filter((id) => id !== generatedTitleId).pop();
        const below = belowId ? modalPanels.get(belowId) : null;
        if (isRestorableFocusTarget(below)) return below;
        return returnFocusRefRef.current?.current ?? null;
      });
    };
  }, [active, generatedTitleId]);

  // 포커스 격납 — 안에 있던 요소가 disabled/언마운트되면(저장 중 버튼, 완료 화면 전환)
  // 포커스가 body로 떨어져 aria-modal 밖에 놓인다. **이때 브라우저는 focusin을 쏘지 않으므로**
  // focusout(다음 프레임에 확인) + focusin(명시적 외부 focus) 둘 다 듣고 최상단 모달이 회수한다.
  useEffect(() => {
    if (!active) return;
    const recapture = () => {
      if (modalStack[modalStack.length - 1] !== generatedTitleId) return;
      const panel = dialogRef.current;
      if (!panel) return;
      const activeEl = document.activeElement;
      if (activeEl instanceof Node && panel.contains(activeEl)) return;
      panel.focus();
    };
    const onFocusOut = () => {
      // focusout은 새 포커스가 자리 잡기 전에 온다 — 다음 프레임에 결과를 본다.
      window.requestAnimationFrame(recapture);
    };
    const onFocusIn = (event: FocusEvent) => {
      const panel = dialogRef.current;
      if (!panel) return;
      const target = event.target;
      if (target instanceof Node && panel.contains(target)) return;
      recapture();
    };
    document.addEventListener('focusout', onFocusOut);
    document.addEventListener('focusin', onFocusIn);
    return () => {
      document.removeEventListener('focusout', onFocusOut);
      document.removeEventListener('focusin', onFocusIn);
    };
  }, [active, generatedTitleId]);

  // body 스크롤 잠금(참조 카운트).
  useEffect(() => {
    if (!active || !lockScroll) return;
    if (scrollLockCount === 0) {
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
    }
    scrollLockCount += 1;
    return () => {
      scrollLockCount -= 1;
      if (scrollLockCount === 0) {
        document.body.style.overflow = previousBodyOverflow ?? '';
        previousBodyOverflow = null;
      }
    };
  }, [active, lockScroll]);

  // Escape 닫기 + Tab focus-trap. 최상단 모달만 반응한다.
  // 스택 등록은 **마운트 생명주기에만** 연동한다 — closeOnEscape(=!busy) 같은 값이 바뀔 때
  // 재등록되면 busy 토글만으로 스택 최상단이 뒤집혀 Escape/Tab이 엉뚱한 모달로 간다.
  useEffect(() => {
    if (!active) return;
    modalStack.push(generatedTitleId);
    const panel = dialogRef.current;
    if (panel) modalPanels.set(generatedTitleId, panel);
    // 스택 최상단이 바뀌었으니 "누구만 살릴지"를 다시 계산한다.
    syncBackgroundInert();
    return () => {
      const idx = modalStack.lastIndexOf(generatedTitleId);
      if (idx !== -1) modalStack.splice(idx, 1);
      modalPanels.delete(generatedTitleId);
      syncBackgroundInert();
    };
  }, [active, generatedTitleId, portalNode]);

  useEffect(() => {
    if (!active) return;
    const handler = (event: KeyboardEvent) => {
      // 중첩 시 최상단 모달만 키를 처리(Escape가 전체를 닫거나 Tab을 서로 뺏는 것 방지).
      if (modalStack[modalStack.length - 1] !== generatedTitleId) return;
      if (event.key === 'Escape' && closeOnEscape) {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const panel = dialogRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) {
        // 포커스 가능한 자식이 없으면 패널 자체에 가둔다.
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      const activeEl = document.activeElement as HTMLElement | null;
      // 패널 자체(tabIndex -1)나 패널 밖에 포커스가 있으면 방향에 따라 양 끝으로 가둔다.
      // (패널 focus 상태에서 Shift+Tab이 뒤 요소로 새는 것을 막는다.)
      if (activeEl === panel || !panel.contains(activeEl)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && activeEl === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeEl === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [active, closeOnEscape, generatedTitleId]);

  const dialogProps: ModalDialogA11y['dialogProps'] = {
    ref: dialogRef,
    tabIndex: -1,
    role: 'dialog',
    'aria-modal': true,
  };
  if (ariaLabel) {
    dialogProps['aria-label'] = ariaLabel;
  } else {
    dialogProps['aria-labelledby'] = titleId;
  }
  if (ariaDescribedBy) {
    dialogProps['aria-describedby'] = ariaDescribedBy;
  }

  return {
    dialogRef,
    portalContainer: portalNode,
    titleId,
    backdropProps: {
      onMouseDown: (event: ReactMouseEvent) => {
        pointerDownOnBackdrop.current = event.target === event.currentTarget;
      },
      onClick: (event: ReactMouseEvent) => {
        const startedOnBackdrop = pointerDownOnBackdrop.current;
        pointerDownOnBackdrop.current = false;
        if (closeOnBackdrop && startedOnBackdrop && event.target === event.currentTarget) {
          onCloseRef.current();
        }
      },
    },
    dialogProps,
  };
}
