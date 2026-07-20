'use client';

import { useRef, type ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { useModalDialog } from '@/lib/useModalDialog';

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
  testId = 'confirm-dialog',
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const { titleId, backdropProps, dialogProps } = useModalDialog({
    onClose: onCancel,
    active: open,
    // 파괴적 확인은 취소 버튼에 기본 포커스를 둬 실수로 Enter를 눌러도 안전하게.
    initialFocusRef: cancelRef,
  });

  if (!open) return null;

  const isDanger = tone === 'danger';

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 p-4"
      data-testid={`${testId}-backdrop`}
      {...backdropProps}
    >
      <div
        {...dialogProps}
        data-testid={testId}
        className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg outline-none"
      >
        <div className="flex items-start gap-3">
          {isDanger && (
            <span className="mt-0.5 rounded-sm bg-error-bg p-2 text-error-text">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-bold text-ink" data-testid={`${testId}-title`}>
              {title}
            </h2>
            {description != null && <p className="mt-1 text-sm text-muted">{description}</p>}
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
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            data-testid={`${testId}-confirm`}
            className={
              isDanger
                ? 'inline-flex h-9 items-center gap-1 rounded-sm bg-error-text px-4 text-sm font-semibold text-white hover:bg-error-text-hover disabled:opacity-50'
                : 'inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-active disabled:opacity-50'
            }
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
