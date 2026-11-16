'use client';

import { bundledMarkerIcon } from '@/lib/markerIconGlyphs';
import { makiIconName, makiIconUrl } from '@/lib/makiIcons';
import type { LucideProps } from 'lucide-react';
import { createElement, useState } from 'react';

/**
 * 마커 아이콘 한 개. `tone="light"`는 색 원 위 흰 아이콘(지도 마커·고르기 칩).
 * maki SVG를 받지 못하면 `marker`로 대신한다.
 */
export function MakiIcon({
  icon,
  title,
  size = 18,
  tone = 'light',
  testId = 'trip-map-maki-icon',
}: {
  icon: string;
  title?: string;
  size?: number;
  tone?: 'light' | 'dark';
  testId?: string;
}) {
  const renderedIcon = makiIconName(icon);
  const [src, setSrc] = useState(() => makiIconUrl(renderedIcon));
  // icon(따라서 renderedIcon)이 바뀌면 이전 onError fallback 상태를 지우고 새 아이콘으로
  // 되돌린다 — src는 onError로도 독립적으로 바뀔 수 있어 순수 파생값이 아니다.
  const [prevRenderedIcon, setPrevRenderedIcon] = useState(renderedIcon);
  if (renderedIcon !== prevRenderedIcon) {
    setPrevRenderedIcon(renderedIcon);
    setSrc(makiIconUrl(renderedIcon));
  }

  const bundled = bundledMarkerIcon(renderedIcon);
  if (bundled) {
    // 정적 매핑에서 고른 아이콘 — 렌더 중 컴포넌트를 만들지 않게 createElement로 그린다(react-hooks).
    // data-* 속성은 LucideProps 타입에 없지만 svg로 그대로 전달된다.
    const props: Record<string, unknown> = {
      'aria-hidden': true,
      'data-testid': testId,
      'data-maki-icon': icon,
      'data-maki-rendered-icon': renderedIcon,
      width: size,
      height: size,
      strokeWidth: 2.25,
      color: tone === 'light' ? '#fff' : 'currentColor',
      className: 'block shrink-0',
    };
    return createElement(
      bundled,
      props as LucideProps,
      title ? <title>{title}</title> : null,
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      aria-hidden="true"
      data-testid={testId}
      data-maki-icon={icon}
      data-maki-rendered-icon={src.endsWith('/marker.svg') ? 'marker' : renderedIcon}
      className="block object-contain"
      width={size}
      height={size}
      style={{
        width: size,
        height: size,
        filter: tone === 'light' ? 'brightness(0) invert(1)' : 'brightness(0)',
      }}
      title={title}
      onError={() => {
        const fallbackSrc = makiIconUrl('marker');
        if (src !== fallbackSrc) setSrc(fallbackSrc);
      }}
    />
  );
}
