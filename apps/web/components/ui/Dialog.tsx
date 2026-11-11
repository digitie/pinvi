'use client';

import {
  Dialog as CommonDialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@kor-travel/ui/dialog';
import { useId, type MouseEvent, type ReactNode, type RefObject } from 'react';
import { X } from 'lucide-react';
import { useDialogFocus } from '@/lib/dialogFocus';

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
  /** 복합 제목의 명시적 접근성 이름. 생략하면 제목을 연결한다. */
  ariaLabel?: string;
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

/** 공개 디자인과 요청 취소 정책만 소유한다. portal/중첩/trap/격리/scroll은 공통 Radix가 소유한다. */
export function Dialog({
  open,
  onClose,
  title,
  ariaLabel,
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
  const titleId = useId();
  const { contentRef, onOpenAutoFocus, onCloseAutoFocus } = useDialogFocus(
    initialFocusRef,
    returnFocusRef,
  );
  const closeWhileBusy = busy ? onCancelBusy : undefined;
  const sheet = variant === 'sheet';
  return (
    <CommonDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent
        unstyled
        showCloseButton={false}
        ref={contentRef}
        onOpenAutoFocus={onOpenAutoFocus}
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (busy) event.preventDefault();
        }}
        // 기존 scrim 계약: pointerdown만으로 닫지 않고 완성된 overlay click을 취소 의도로 받는다.
        onPointerDownOutside={(event) => event.preventDefault()}
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabel ? undefined : titleId}
        {...(description == null ? { 'aria-describedby': undefined } : {})}
        tabIndex={-1}
        data-testid={testId}
        overlayProps={{
          'data-testid': testId + '-backdrop',
          className: 'fixed inset-0 z-modal bg-scrim/50',
          onClick: (event: MouseEvent<HTMLDivElement>) => {
            if (!busy && event.target === event.currentTarget) onClose();
          },
        }}
        className={`fixed left-1/2 z-modal flex max-h-[88dvh] min-w-0 -translate-x-1/2 flex-col overflow-hidden border border-hairline bg-canvas shadow-overlay outline-hidden ${
          sheet
            ? 'bottom-0 top-auto w-full max-w-full translate-y-0 rounded-t-xl sm:bottom-auto sm:top-1/2 sm:-translate-y-1/2 sm:rounded-md'
            : 'top-1/2 w-[calc(100%-2rem)] max-w-full -translate-y-1/2 rounded-md'
        } ${SIZE[size]}`}
      >
        <div className="flex min-w-0 items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            <DialogTitle
              id={titleId}
              className="text-base font-bold text-ink [overflow-wrap:anywhere]"
              data-testid={testId + '-title'}
            >
              {title}
            </DialogTitle>
            {description != null ? (
              <DialogDescription id={titleId + '-desc'} className="mt-1 text-sm text-muted">
                {description}
              </DialogDescription>
            ) : null}
          </div>
          {showClose ? (
            <button
              type="button"
              onClick={closeWhileBusy ?? onClose}
              disabled={busy && !closeWhileBusy}
              aria-label={closeWhileBusy ? '취소하고 닫기' : '닫기'}
              data-testid={testId + '-close'}
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
      </DialogContent>
    </CommonDialog>
  );
}
