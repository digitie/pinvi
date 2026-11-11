'use client';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@kor-travel/ui/alert-dialog';
import { buttonClassName } from '@/components/ui/button-styles';
import { useDialogFocus } from '@/lib/dialogFocus';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useId, useRef, type MouseEvent, type ReactNode, type RefObject } from 'react';

/**
 * 제네릭 확인 다이얼로그(TDR, ADR-056).
 *
 * day-plan 삭제 경고(F2)처럼 되돌릴 수 없는 조작 앞에 두는 공통 컴포넌트.
 * `tone="danger"`면 경고 아이콘 + 빨간 확인 버튼으로 파괴성을 드러내고,
 * 기본 포커스를 취소 버튼에 둔다(오조작 방지). 부가 내용(삭제될 POI 목록 등)은
 * `children`으로 넣는다.
 */
export interface ConfirmDialogProps {
  /** true일 때만 렌더한다(controlled). */
  open: boolean;
  title: string;
  description?: ReactNode;
  /** 확인 버튼 라벨. 기본 '확인'. */
  confirmLabel?: string;
  /** 취소 버튼 라벨. 기본 '취소'. */
  cancelLabel?: string;
  /** 'danger'면 파괴적 스타일(경고 아이콘 + 빨간 버튼 + 취소 기본 포커스). */
  tone?: 'default' | 'danger';
  /** 진행 중이면 스피너 표시 + 버튼 비활성. */
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** 본문 아래 부가 내용(예: 삭제될 항목 목록). */
  children?: ReactNode;
  /** 닫힐 때 포커스를 돌려줄 트리거. 트리거가 busy로 disabled된 채 열렸을 때의 폴백. */
  returnFocusRef?: RefObject<HTMLElement | null>;
  /** e2e용 testid 접두어. 기본 'confirm-dialog'. */
  testId?: string;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '확인',
  cancelLabel = '취소',
  tone = 'default',
  busy = false,
  onConfirm,
  onCancel,
  children,
  returnFocusRef,
  testId = 'confirm-dialog',
}: ConfirmDialogProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const { contentRef, onOpenAutoFocus, onCloseAutoFocus } = useDialogFocus(
    cancelRef,
    returnFocusRef,
  );
  const isDanger = tone === 'danger';
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onCancel();
      }}
    >
      <AlertDialogContent
        unstyled
        ref={contentRef}
        onOpenAutoFocus={onOpenAutoFocus}
        onCloseAutoFocus={onCloseAutoFocus}
        onEscapeKeyDown={(event) => {
          if (busy) event.preventDefault();
        }}
        aria-modal="true"
        aria-labelledby={titleId}
        {...(description == null ? { 'aria-describedby': undefined } : {})}
        tabIndex={-1}
        data-testid={testId}
        overlayProps={{
          'data-testid': testId + '-backdrop',
          className: 'fixed inset-0 z-modal bg-scrim/50',
          // AlertDialog은 outside dismiss를 막는다. 기존 scrim 클릭은 명시적 취소 의도로 연결한다.
          onClick: (event: MouseEvent<HTMLDivElement>) => {
            if (!busy && event.target === event.currentTarget) onCancel();
          },
        }}
        className="fixed left-1/2 top-1/2 z-modal max-h-[88dvh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 overflow-y-auto rounded-md border border-hairline bg-canvas p-5 shadow-overlay outline-hidden"
      >
        <div className="flex items-start gap-3">
          {isDanger && (
            <span className="mt-0.5 rounded-sm bg-error-bg p-2 text-error-text">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <AlertDialogTitle
              id={titleId}
              className="text-base font-bold text-ink"
              data-testid={testId + '-title'}
            >
              {title}
            </AlertDialogTitle>
            {description != null && (
              <AlertDialogDescription className="mt-1 text-sm text-muted">
                {description}
              </AlertDialogDescription>
            )}
          </div>
        </div>
        {children != null && <div className="text-sm text-ink">{children}</div>}
        <div className="flex flex-wrap justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
            data-testid={testId + '-cancel'}
            className={buttonClassName({ variant: 'secondary', size: 'sm' })}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            data-testid={testId + '-confirm'}
            className={buttonClassName({ variant: isDanger ? 'danger' : 'primary', size: 'sm' })}
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </button>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
