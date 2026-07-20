'use client';

import { useRef, type ReactNode } from 'react';
import { AlertTriangle, Loader2, X } from 'lucide-react';
import { useModalDialog } from '@/lib/useModalDialog';

/**
 * Feature 상세 풀스크린 모달의 **shell**(TDR, ADR-056, F5).
 *
 * 데스크톱은 가운데 정렬 모달, 모바일은 하단 bottom-sheet로 뜬다(반응형은 CSS만으로).
 * kind별 detail-card 본문은 이 shell 위에 `children`으로 올린다(T-309c). 외부
 * enrichment 출처 표기/링크는 `footer` 슬롯에 둔다. loading/error는 본문 슬롯을
 * 대체한다. 데이터 계약(`GET /features/{id}/detail-card`)에는 의존하지 않는 순수
 * 표현 컴포넌트다.
 */
export interface FeatureDetailModalProps {
  /** true일 때만 렌더한다(controlled). */
  open: boolean;
  title: string;
  /** 제목 아래 보조 텍스트(카테고리/주소 등). */
  subtitle?: ReactNode;
  /** true면 본문 대신 로딩 표시. */
  loading?: boolean;
  /** 있으면 본문 대신 에러 표시. */
  error?: ReactNode;
  onClose: () => void;
  /** kind별 detail-card 본문(T-309c에서 채움). */
  children?: ReactNode;
  /** 하단 고정 영역(외부 enrichment 출처 표기 + Kakao/Naver 링크 등). */
  footer?: ReactNode;
  /** e2e용 testid 접두어. 기본 'feature-detail-modal'. */
  testId?: string;
}

export function FeatureDetailModal({
  open,
  title,
  subtitle,
  loading = false,
  error,
  onClose,
  children,
  footer,
  testId = 'feature-detail-modal',
}: FeatureDetailModalProps) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const { titleId, backdropProps, dialogProps } = useModalDialog({
    onClose,
    active: open,
    initialFocusRef: closeRef,
  });

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      data-testid={`${testId}-backdrop`}
      {...backdropProps}
    >
      <div
        {...dialogProps}
        data-testid={testId}
        className="flex max-h-[88vh] w-full flex-col overflow-hidden rounded-t-xl border border-hairline bg-white shadow-lg outline-none sm:max-h-[85vh] sm:max-w-lg sm:rounded-md"
      >
        <header className="flex items-start justify-between gap-3 border-b border-hairline px-5 py-4">
          <div className="min-w-0">
            <h2
              id={titleId}
              className="truncate text-base font-bold text-ink"
              data-testid={`${testId}-title`}
            >
              {title}
            </h2>
            {subtitle != null && <p className="mt-0.5 truncate text-sm text-muted">{subtitle}</p>}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="닫기"
            data-testid={`${testId}-close`}
            className="-mr-1 -mt-1 shrink-0 rounded-sm p-1.5 text-muted hover:bg-surface-soft hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4" data-testid={`${testId}-body`}>
          {loading ? (
            <div
              className="flex items-center gap-2 py-8 text-sm text-muted"
              data-testid={`${testId}-loading`}
            >
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              불러오는 중...
            </div>
          ) : error != null ? (
            <div
              className="flex items-start gap-2 py-6 text-sm text-error-text"
              data-testid={`${testId}-error`}
              role="alert"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          ) : (
            children
          )}
        </div>

        {footer != null && (
          <footer
            className="border-t border-hairline px-5 py-3 text-xs text-muted"
            data-testid={`${testId}-footer`}
          >
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
