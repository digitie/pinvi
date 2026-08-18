'use client';

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
  /** 진행 중이면 backdrop/Escape 닫기를 막는다(저장 중 이탈 방지). */
  busy?: boolean;
  /** 헤더 우측 닫기(×) 버튼. 기본 true. */
  showClose?: boolean;
  /** 열릴 때 포커스를 옮길 대상. 생략하면 패널. */
  initialFocusRef?: RefObject<HTMLElement | null>;
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
  showClose = true,
  initialFocusRef,
  footer,
  children,
  testId = 'dialog',
}: DialogProps) {
  const { titleId, backdropProps, dialogProps } = useModalDialog({
    onClose,
    active: open,
    // 저장 중에는 실수로 닫혀 작업이 사라지지 않게 잠근다.
    closeOnEscape: !busy,
    closeOnBackdrop: !busy,
    initialFocusRef,
  });

  if (!open) return null;

  const sheet = variant === 'sheet';

  return (
    <div
      className={`fixed inset-0 z-modal flex justify-center bg-scrim/50 ${
        sheet ? 'items-end p-0 sm:items-center sm:p-4' : 'items-center p-4'
      }`}
      data-testid={`${testId}-backdrop`}
      {...backdropProps}
    >
      <div
        {...dialogProps}
        data-testid={testId}
        className={`flex max-h-[88dvh] w-full flex-col overflow-hidden border border-hairline bg-canvas shadow-overlay outline-none ${
          sheet ? 'rounded-t-xl sm:rounded-md' : 'rounded-md'
        } ${SIZE[size]}`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="text-base font-bold text-ink [overflow-wrap:anywhere]"
              data-testid={`${testId}-title`}
            >
              {title}
            </h2>
            {description != null ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          </div>
          {showClose ? (
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              aria-label="닫기"
              data-testid={`${testId}-close`}
              className="focus-ring -mr-2 -mt-1 inline-flex size-11 shrink-0 items-center justify-center rounded-sm text-muted transition-colors duration-normal ease-pinvi hover:bg-surface-soft hover:text-ink disabled:cursor-not-allowed"
            >
              <X className="size-5" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-5 py-4">{children}</div>

        {footer != null ? (
          <div className="flex flex-wrap justify-end gap-2 border-t border-hairline px-5 py-4">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  );
}
