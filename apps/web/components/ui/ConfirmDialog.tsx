'use client';

import { createPortal } from 'react-dom';
import { useRef, type ReactNode, type RefObject } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useModalDialog } from '@/lib/useModalDialog';
import { buttonClassName } from '@/components/ui/Button';

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
  const descriptionId = `${testId}-description`;
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const { titleId, portalContainer, backdropProps, dialogProps } = useModalDialog({
    onClose: onCancel,
    active: open,
    // 파괴적 확인은 취소 버튼에 기본 포커스를 둬 실수로 Enter를 눌러도 안전하게.
    initialFocusRef: cancelRef,
    returnFocusRef,
    // Dialog 프리미티브와 같은 계약 — 진행 중에는 Escape/backdrop도 잠근다
    // (버튼만 잠그고 Escape는 열려 있으면 '취소는 못 누르는데 Escape는 먹는' 모순).
    closeOnEscape: !busy,
    closeOnBackdrop: !busy,
    ariaDescribedBy: description != null ? descriptionId : undefined,
  });

  if (!open) return null;
  // portal 컨테이너는 마운트 effect에서 생긴다 — 생기기 전에는 렌더하지 않는다
  // (앱 트리 안에서 잠깐 떴다가 옮겨지면 배경 inert가 자기 자신을 잠근다).
  if (!portalContainer) return null;

  const isDanger = tone === 'danger';

  return createPortal(
    <div
      className="fixed inset-0 z-modal flex items-center justify-center bg-scrim/50 p-4"
      data-testid={`${testId}-backdrop`}
      {...backdropProps}
    >
      <div
        {...dialogProps}
        data-testid={testId}
        className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-canvas p-5 shadow-overlay outline-hidden"
      >
        <div className="flex items-start gap-3">
          {isDanger && (
            <span className="mt-0.5 rounded-sm bg-error-bg p-2 text-error-text">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h2
              id={titleId}
              className="text-base font-bold text-ink"
              data-testid={`${testId}-title`}
            >
              {title}
            </h2>
            {description != null && (
              <p id={descriptionId} className="mt-1 text-sm text-muted">
                {description}
              </p>
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
            data-testid={`${testId}-cancel`}
            className={buttonClassName({ variant: 'secondary', size: 'sm' })}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            data-testid={`${testId}-confirm`}
            className={buttonClassName({ variant: isDanger ? 'danger' : 'primary', size: 'sm' })}
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    portalContainer,
  );
}
