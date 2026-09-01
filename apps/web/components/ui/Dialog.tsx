'use client';

import { createPortal } from 'react-dom';
import type { ReactNode, RefObject } from 'react';
import { X } from 'lucide-react';
import { useModalDialog } from '@/lib/useModalDialog';

/* Hallmark · component: dialog · genre: modern-minimal · theme: pinvi-locked(DESIGN.md)
 * states: closed · open · busy · error(호출부 슬롯) · scrim/overlay 토큰 · focus-trap/scroll-lock(useModalDialog)
 */

export type DialogSize = 'sm' | 'md' | 'lg';
/** `center`=데스크톱 중앙, `sheet`=모바일 하단 시트 + sm↑ 중앙(지도 상세 등). */
export type DialogVariant = 'center' | 'sheet';

const SIZE: Record<DialogSize, string> = {
  sm: 'sm:max-w-md',
  md: 'sm:max-w-lg',
  lg: 'sm:max-w-3xl',
};

export interface DialogProps {
  /** true일 때만 렌더한다(controlled). */
  open: boolean;
  /** Escape·backdrop·닫기 버튼 공통 콜백. */
  onClose: () => void;
  /** 제목 — 문자열이면 h2로 렌더하고 aria-labelledby를 건다. */
  title: ReactNode;
  /** 제목 아래 보조 설명. */
  description?: ReactNode;
  size?: DialogSize;
  variant?: DialogVariant;
  /**
   * 진행 중이면 **실수로** 닫히는 경로(Escape·backdrop)를 잠근다.
   *
   * 명시적 닫기(×)까지 잠글지는 `onCancelBusy`가 결정한다:
   * - 주지 않으면 × 도 잠근다 — 진행 중 요청을 취소할 방법이 없는 다이얼로그에서 닫기만 열어 두면
   *   닫은 다이얼로그가 늦은 응답으로 되살아나거나 비멱등 POST가 중복된다(T-315 2차 리뷰 실측).
   * - 주면 × 는 활성으로 남고, 누르면 그 콜백이 in-flight 요청을 취소한 뒤 닫는다
   *   (T-316 요청 수명 계약 ⑤ — 탈출구는 취소와 함께 제공한다).
   */
  busy?: boolean;
  /**
   * busy 중 명시적 닫기 경로. 진행 중 요청을 **취소**하고 닫는 책임을 호출부가 진다.
   * 주면 busy에도 × 가 활성으로 남는다.
   */
  onCancelBusy?: () => void;
  /** 헤더 우측 닫기(×) 버튼. 기본 true. */
  showClose?: boolean;
  /** 열릴 때 포커스를 옮길 대상. 생략하면 패널. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** 닫힐 때 포커스를 돌려줄 트리거. 직전 포커스가 disabled/제거됐을 때의 폴백. */
  returnFocusRef?: RefObject<HTMLElement | null>;
  /** 하단 액션 행(버튼들). */
  footer?: ReactNode;
  children?: ReactNode;
  /** e2e용 testid 접두어. `<testId>-backdrop|-title|-close`가 함께 붙는다. */
  testId?: string;
}

/**
 * 모달 셸 프리미티브 — backdrop(scrim) + 패널 + 헤더/본문/푸터 슬롯.
 *
 * 저장소 곳곳(10곳)이 `fixed inset-0 … bg-scrim/50` 셸과 focus/Escape/scroll-lock 배선을 손으로
 * 복사하고 z-index를 임의값(`z-[60]`/`z-[70]`)으로 두던 것을 한 컴포넌트로 모은다(Hallmark audit Mj4).
 * a11y·중첩 모달·backdrop 드래그 처리는 전부 `useModalDialog`가 담당하고, 여기서는 토큰
 * (`bg-scrim/50`, `shadow-overlay`, `z-modal`, `rounded-md`)과 레이아웃만 고정한다.
 */
export function Dialog({
  open,
  onClose,
  title,
  description,
  size = 'md',
  variant = 'center',
  busy = false,
  onCancelBusy,
  showClose = true,
  initialFocusRef,
  returnFocusRef,
  footer,
  children,
  testId = 'dialog',
}: DialogProps) {
  const descriptionId = `${testId}-desc`;
  // busy 중 닫기는 "진행 중 요청 취소"라는 다른 의미다 — 호출부가 그 경로를 줬을 때만 연다.
  const closeWhileBusy = busy ? onCancelBusy : undefined;
  const closeDisabled = busy && !closeWhileBusy;
  const { titleId, portalContainer, requestClose, backdropProps, dialogProps } = useModalDialog({
    onClose,
    active: open,
    // 저장 중에는 실수로 닫혀 작업이 사라지지 않게 잠근다(T-315 2차 리뷰: 닫기만 열어 두면
    // 늦은 응답이 닫은 다이얼로그를 되살리고 비멱등 POST가 중복된다).
    closeOnEscape: !busy,
    closeOnBackdrop: !busy,
    initialFocusRef,
    returnFocusRef,
    ariaDescribedBy: description != null ? descriptionId : undefined,
  });

  if (!open) return null;
  // portal 컨테이너는 마운트 effect에서 생긴다 — 생기기 전에는 렌더하지 않는다
  // (앱 트리 안에서 잠깐 떴다가 옮겨지면 배경 inert가 자기 자신을 잠근다).
  if (!portalContainer) return null;

  const sheet = variant === 'sheet';

  return createPortal(
    <div
      className={`fixed inset-0 z-modal flex min-w-0 max-w-full justify-center overflow-x-clip bg-scrim/50 ${
        sheet ? 'items-end p-0 sm:items-center sm:p-4' : 'items-center p-4'
      }`}
      data-testid={`${testId}-backdrop`}
      {...backdropProps}
    >
      <div
        {...dialogProps}
        data-testid={testId}
        className={`flex max-h-[88dvh] w-full min-w-0 max-w-full flex-col overflow-hidden border border-hairline bg-canvas shadow-overlay outline-hidden ${
          sheet ? 'rounded-t-xl sm:rounded-md' : 'rounded-md'
        } ${SIZE[size]}`}
      >
        <div className="flex min-w-0 items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="text-base font-bold text-ink [overflow-wrap:anywhere]"
              data-testid={`${testId}-title`}
            >
              {title}
            </h2>
            {description != null ? (
              <p id={descriptionId} className="mt-1 text-sm text-muted">
                {description}
              </p>
            ) : null}
          </div>
          {showClose ? (
            <button
              type="button"
              onClick={closeWhileBusy ?? requestClose}
              disabled={closeDisabled}
              aria-label={closeWhileBusy ? '취소하고 닫기' : '닫기'}
              data-testid={`${testId}-close`}
              className="focus-ring -mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-sm text-muted transition-colors duration-normal ease-pinvi hover:bg-surface-soft hover:text-ink disabled:cursor-not-allowed"
            >
              <X className="size-5" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <div className="min-h-0 min-w-0 flex-1 overflow-auto px-5 py-4">{children}</div>

        {footer != null ? (
          <div className="flex min-w-0 flex-wrap justify-end gap-2 border-t border-hairline px-5 py-4">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    portalContainer,
  );
}
