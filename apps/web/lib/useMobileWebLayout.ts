'use client';

import { useEffect, useState } from 'react';

/**
 * 모바일 웹 레이아웃 판정 — **뷰포트·포인터 능력만** 본다(UA 스니핑 없음, Hallmark audit Mj9).
 * 폭 ≤1023px이거나, 터치 가능한 coarse pointer 기기면 모바일 레이아웃.
 * UA 정규식은 태블릿/데스크톱 터치 기기를 오분류하고 SSR과 클라이언트 판정이 갈라져 제거했다.
 */
const MOBILE_LAYOUT_QUERY = '(max-width: 1023px), (pointer: coarse) and (hover: none)';

export function useMobileWebLayout() {
  // SSR/최초 페인트는 데스크톱 레이아웃(false)에서 시작해 hydration 직후 보정한다.
  const [mobileWebLayout, setMobileWebLayout] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_LAYOUT_QUERY);
    const update = (event: MediaQueryList | MediaQueryListEvent) =>
      setMobileWebLayout(event.matches);

    update(media);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return mobileWebLayout;
}
