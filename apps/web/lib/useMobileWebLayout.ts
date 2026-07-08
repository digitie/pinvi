'use client';

import { useEffect, useState } from 'react';

const MOBILE_WIDTH_QUERY = '(max-width: 1023px)';
const COARSE_POINTER_QUERY = '(pointer: coarse)';
const MOBILE_BROWSER_RE = /SamsungBrowser|Android|Mobile|iPhone|iPad|iPod/i;

function shouldUseMobileWebLayout() {
  if (typeof window === 'undefined') {
    return false;
  }

  return (
    window.matchMedia(MOBILE_WIDTH_QUERY).matches ||
    (window.navigator.maxTouchPoints > 0 && window.matchMedia(COARSE_POINTER_QUERY).matches) ||
    MOBILE_BROWSER_RE.test(window.navigator.userAgent)
  );
}

export function useMobileWebLayout() {
  const [mobileWebLayout, setMobileWebLayout] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(MOBILE_WIDTH_QUERY);
    const update = () => setMobileWebLayout(shouldUseMobileWebLayout());

    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return mobileWebLayout;
}
