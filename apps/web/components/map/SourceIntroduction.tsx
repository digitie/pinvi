'use client';

import type { SourceImage, SourceIntroduction as SourceIntroductionData } from '@pinvi/schemas';
import { ExternalLink } from 'lucide-react';
import { useId, useState } from 'react';

/** 이 길이 또는 줄 수를 넘는 소개문만 접어 두고 "더 보기"를 단다. */
const COLLAPSE_MIN_CHARS = 140;
const COLLAPSE_MIN_LINES = 4;

function needsCollapse(text: string): boolean {
  return text.length > COLLAPSE_MIN_CHARS || text.split('\n').length > COLLAPSE_MIN_LINES;
}

/**
 * 원본 이미지 1장 — 원본 URL을 그대로 보이고 원본으로 연결한다. 공공누리 제3유형(변경금지)을 지키려고
 * 모든 이미지를 크롭·필터 없이 원본 비율(`object-contain`)로만 그린다. 불러오지 못하면 부모가 숨긴다.
 */
function OriginalImage({
  image,
  testId,
  onError,
}: {
  image: SourceImage;
  testId: string;
  onError: () => void;
}) {
  return (
    <a
      href={image.url}
      target="_blank"
      rel="noopener noreferrer"
      referrerPolicy="no-referrer"
      className="block overflow-hidden rounded-sm border border-hairline bg-surface-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      aria-label={`${image.alt} — 원본 이미지 새 창으로 보기`}
      data-testid={`${testId}-image-link`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- 원본 그대로 표시(next/image 최적화 = 변형 금지) */}
      <img
        src={image.url}
        alt={image.alt}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        onError={onError}
        className="mx-auto block h-auto max-h-56 w-auto max-w-full object-contain"
        data-testid={`${testId}-image`}
        data-no-derivatives={image.no_derivatives ? 'true' : 'false'}
      />
    </a>
  );
}

export interface SourceIntroductionProps {
  introduction: SourceIntroductionData;
  testId: string;
}

/**
 * 출처 장소 소개(TourAPI — 한국관광공사): 대표 이미지 · 소개문(길면 접기) · 출처/공공누리 표시.
 *
 * 소개문은 서버가 HTML을 걷어 낸 평문이고 여기서도 텍스트로만 그린다(`dangerouslySetInnerHTML` 금지).
 * 출처 표시는 이미지·소개문 중 하나라도 보이면 늘 함께 보인다.
 */
export function SourceIntroduction({ introduction, testId }: SourceIntroductionProps) {
  const overviewId = useId();
  const [expanded, setExpanded] = useState(false);
  // 불러오지 못한 이미지는 빈 틀을 남기지 않고 뺀다 — 다 빠지고 소개문도 없으면 블록째 숨긴다.
  const [failedUrls, setFailedUrls] = useState<ReadonlySet<string>>(() => new Set());
  const { overview } = introduction;
  const images = introduction.images.filter((image) => !failedUrls.has(image.url));
  if (!overview && images.length === 0) return null;
  const collapsible = overview ? needsCollapse(overview) : false;
  return (
    <div className="space-y-2" data-testid={testId}>
      {images.map((image) => (
        <OriginalImage
          key={image.url}
          image={image}
          testId={testId}
          onError={() => setFailedUrls((prev) => new Set(prev).add(image.url))}
        />
      ))}
      {overview && (
        <div>
          <p
            id={overviewId}
            className={`whitespace-pre-line break-words text-sm text-body ${
              collapsible && !expanded ? 'line-clamp-4' : ''
            }`}
            data-testid={`${testId}-overview`}
          >
            {overview}
          </p>
          {collapsible && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
              aria-controls={overviewId}
              className="mt-1 inline-flex min-h-11 items-center text-xs font-semibold text-legal-link hover:underline"
              data-testid={`${testId}-overview-toggle`}
            >
              {expanded ? '소개 접기' : '소개 더 보기'}
            </button>
          )}
        </div>
      )}
      <p
        className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted"
        data-testid={`${testId}-attribution`}
      >
        <span>출처: {introduction.attribution}</span>
        {/* 공공누리 유형은 이미지에 걸린 조건이라, 보이는 이미지가 있을 때만 단다. */}
        {images.length > 0 && introduction.license_label && introduction.license_url && (
          <>
            <span aria-hidden="true">·</span>
            <a
              href={introduction.license_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 text-legal-link hover:underline"
              data-testid={`${testId}-license`}
              data-kogl-type={introduction.kogl_type ?? undefined}
            >
              {introduction.license_label}
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
              <span className="sr-only">(새 창)</span>
            </a>
          </>
        )}
      </p>
    </div>
  );
}
