import Link from 'next/link';
import type { ReactNode } from 'react';
import { Wordmark } from './Wordmark';
import { LEGAL_DOC_TITLES, LEGAL_SLUGS } from '@/lib/legalDocs';

/**
 * 공개 표면(랜딩·인증·공유 뷰·404) 공용 chrome — DESIGN.md "Hallmark 잠금 시스템" nav N1a + footer Ft2.
 * 얇은 masthead(워드마크 + 문맥 액션 1~2개) / 1줄 colophon(법무 링크). 앱 셸(AppShell)과 별개.
 * 320px에서도 한 줄: 액션은 호출부가 최대 2개, 라벨 짧게.
 */
export function PublicMasthead({ actions }: { actions?: ReactNode }) {
  return (
    <header className="border-b border-hairline bg-canvas">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between gap-3 px-6">
        <Wordmark />
        {actions ? <nav className="flex items-center gap-1 sm:gap-2">{actions}</nav> : null}
      </div>
    </header>
  );
}

// 법무 문서 목록에서 파생한다 — 문서를 추가하면 colophon 링크가 자동으로 따라온다
// (수기 목록이라 `location-consent`가 빠져 그 문서만 도달 불가였다, T-316 리뷰 P3).
const LEGAL_LINKS = LEGAL_SLUGS.map((slug) => ({
  href: `/legal/${slug}`,
  label: LEGAL_DOC_TITLES[slug],
}));

export function PublicColophon() {
  return (
    <footer className="border-t border-hairline bg-canvas">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-2 px-6 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
        <p className="m-0">© 2026 Pinvi · 한국 여행 계획·기록·공유</p>
        <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0">
          {LEGAL_LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="focus-ring inline-flex min-h-11 items-center rounded-sm text-ink underline decoration-hairline underline-offset-4 hover:decoration-ink"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
