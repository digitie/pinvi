'use client';

import {
  introductionNeedsCollapse,
  sourceAttributionLine,
  visibleIntroductionImages,
} from '@pinvi/domain';
import type { SourceImage, SourceIntroduction as SourceIntroductionData } from '@pinvi/schemas';
import { ExternalLink } from 'lucide-react';
import { useId, useState } from 'react';

const LINK_CLASS = 'text-ink underline underline-offset-2 hover:text-body';

/**
 * 원본 이미지 1장 + 그 이미지의 공공누리 표시. 원본 URL을 그대로 보이고 원본으로 연결한다. 변경금지
 * (제3·4유형)를 지키려고 모든 이미지를 크롭·필터·모서리 깎기 없이 원본 비율(`object-contain`)로만 그린다.
 * 자리는 고정 높이 틀로 미리 잡아 이미지가 늦게 떠도 아래 내용이 밀리지 않는다. 불러오지 못하면 부모가
 * 틀과 공공누리 표시를 함께 뺀다. 공공누리 유형은 이미지마다 다를 수 있어 이미지마다 붙인다.
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
    <figure className="space-y-1" data-testid={`${testId}-figure`}>
      <a
        href={image.url}
        target="_blank"
        rel="noopener noreferrer"
        referrerPolicy="no-referrer"
        className="flex h-56 items-center justify-center border border-hairline bg-surface-soft p-1 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
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
          className="block max-h-full max-w-full object-contain"
          data-testid={`${testId}-image`}
          data-no-derivatives={image.no_derivatives ? 'true' : 'false'}
        />
      </a>
      <figcaption className="text-xs text-muted">
        <a
          href={image.license_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex items-center gap-0.5 ${LINK_CLASS}`}
          data-testid={`${testId}-license`}
          data-kogl-type={image.kogl_type}
        >
          {image.license_label}
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
          <span className="sr-only">(새 창)</span>
        </a>
      </figcaption>
    </figure>
  );
}

export interface SourceIntroductionProps {
  introduction: SourceIntroductionData;
  testId: string;
  /**
   * 불러오지 못한 이미지 URL. 부모(장소 정보 패널)가 넘기면 부모가 "보여 줄 것이 있는지"를 같은 기준으로
   * 판정해 빈 항목을 만들지 않는다. 넘기지 않으면 이 컴포넌트가 스스로 기억한다.
   */
  failedImageUrls?: ReadonlySet<string>;
  onImageError?: (url: string) => void;
}

/**
 * 출처 장소 소개: 원본 이미지(여러 장이면 가로 갤러리) · 소개문(길면 접기) · 출처(+ 기준일).
 *
 * 소개문은 서버가 HTML을 걷어 낸 평문이고 여기서도 텍스트로만 그린다(`dangerouslySetInnerHTML` 금지).
 * 출처 표시는 이미지·소개문 중 하나라도 보이면 늘 함께 보인다. 공공누리 표시는 이미지마다 붙는다.
 */
export function SourceIntroduction({
  introduction,
  testId,
  failedImageUrls,
  onImageError,
}: SourceIntroductionProps) {
  const overviewId = useId();
  const [expanded, setExpanded] = useState(false);
  const [ownFailed, setOwnFailed] = useState<ReadonlySet<string>>(() => new Set());
  const failed = failedImageUrls ?? ownFailed;
  const markFailed = (url: string) => {
    if (onImageError) onImageError(url);
    else setOwnFailed((prev) => new Set(prev).add(url));
  };
  const { overview } = introduction;
  // 깨진 이미지·허용 밖 이미지는 빈 틀을 남기지 않고 뺀다 — 다 빠지고 소개문도 없으면 블록째 숨긴다.
  const images = visibleIntroductionImages(introduction, failed);
  if (!overview && images.length === 0) return null;
  const collapsible = overview ? introductionNeedsCollapse(overview) : false;
  return (
    <div className="space-y-2" data-testid={testId} data-provider={introduction.provider}>
      {images.length === 1 && (
        <OriginalImage
          image={images[0]!}
          testId={testId}
          onError={() => markFailed(images[0]!.url)}
        />
      )}
      {images.length > 1 && (
        <ul
          className="flex snap-x gap-2 overflow-x-auto pb-1"
          aria-label={`사진 ${images.length}장`}
          data-testid={`${testId}-gallery`}
        >
          {images.map((image) => (
            <li key={image.url} className="w-[85%] shrink-0 snap-start">
              <OriginalImage image={image} testId={testId} onError={() => markFailed(image.url)} />
            </li>
          ))}
        </ul>
      )}
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
              className={`mt-1 inline-flex min-h-11 items-center text-xs font-semibold ${LINK_CLASS}`}
              data-testid={`${testId}-overview-toggle`}
            >
              {expanded ? '소개 접기' : '소개 더 보기'}
            </button>
          )}
        </div>
      )}
      <p className="text-xs text-muted" data-testid={`${testId}-attribution`}>
        {sourceAttributionLine(introduction)}
      </p>
    </div>
  );
}
