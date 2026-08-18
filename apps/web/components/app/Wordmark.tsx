import Link from 'next/link';

/**
 * Pinvi 마크 — 핀 실루엣 + 경로 점(Tier-B 손그림 SVG, `docs/design/marker-palette.md`의 핀 형태 미러).
 * 색은 토큰만: `currentColor`(기본 Rausch `text-primary`). favicon.svg / 앱 아이콘과 같은 path.
 */
export function PinviMark({ className = 'size-6' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 21.5s-6.5-6.2-6.5-11.3a6.5 6.5 0 0 1 13 0c0 5.1-6.5 11.3-6.5 11.3Z" />
      <path d="M8.6 9.4 12 13.2l3.4-3.8" />
      <circle cx="8.6" cy="9.4" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="13.2" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="15.4" cy="9.4" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** 워드마크 — 마크(Rausch) + 로고타입(ink 700). 공개 표면과 앱 셸이 같은 것을 쓴다. */
export function Wordmark({ href = '/', className = '' }: { href?: string; className?: string }) {
  return (
    <Link
      href={href}
      className={`focus-ring inline-flex min-h-11 items-center gap-2 rounded-sm text-ink ${className}`}
      aria-label="Pinvi 홈"
    >
      <PinviMark className="size-6 text-primary" />
      <span className="text-lg font-bold tracking-tight">Pinvi</span>
    </Link>
  );
}
