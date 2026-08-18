'use client';

import type { ReactNode } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { Dialog } from '@/components/ui/Dialog';

/**
 * Feature 상세 풀스크린 모달의 **shell**(TDR, ADR-056, F5).
 *
 * 셸 자체는 `components/ui/Dialog` 프리미티브(`variant="sheet"`)가 담당한다 — 데스크톱은
 * 가운데 정렬, 모바일은 하단 bottom-sheet(반응형은 CSS만으로). 이 컴포넌트는 그 위에
 * feature 상세 특유의 loading/error 슬롯과 출처 캡션 footer만 얹는다. kind별 detail-card
 * 본문은 `children`으로 올린다(T-309c). 데이터 계약(`GET /features/{id}/detail-card`)에는
 * 의존하지 않는 순수 표현 컴포넌트다.
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
  return (
    <Dialog
      open={open}
      onClose={onClose}
      // 이관 전 헤더와 동일하게 한 줄 유지 — 긴 POI명/주소가 본문 영역을 밀어내지 않는다.
      title={<span className="block truncate">{title}</span>}
      description={
        subtitle != null ? <span className="block truncate">{subtitle}</span> : undefined
      }
      variant="sheet"
      size="md"
      testId={testId}
      footer={
        footer != null ? (
          // 액션 행이 아니라 출처 캡션 — 폭을 채워 왼쪽 정렬로 읽히게 한다.
          <div className="w-full text-xs text-muted" data-testid={`${testId}-footer`}>
            {footer}
          </div>
        ) : null
      }
    >
      <div data-testid={`${testId}-body`}>
        {loading ? (
          <div
            className="flex items-center gap-2 py-8 text-sm text-muted"
            data-testid={`${testId}-loading`}
            aria-busy="true"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            불러오는 중…
          </div>
        ) : error != null ? (
          <div
            className="flex items-start gap-2 py-6 text-sm text-error-text"
            data-testid={`${testId}-error`}
            role="alert"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        ) : (
          children
        )}
      </div>
    </Dialog>
  );
}
