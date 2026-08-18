'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import {
  CalendarDays,
  LayoutDashboard,
  Map,
  MoreHorizontal,
  Newspaper,
  Paperclip,
  Settings,
  UserCircle,
} from 'lucide-react';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';
import { Wordmark } from '@/components/app/Wordmark';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md · designed-as-app
 * nav: 데스크톱 = ink 밑줄 탭(활성 1개) · 모바일 = 하단 탭바 4 + 더보기 시트 · footer: 없음(앱 셸)
 * ground: bg-canvas(회색 ground 위 흰 카드 남발 폐기, T-314)
 */
const NAV_ITEMS = [
  { href: '/', label: '홈', icon: LayoutDashboard },
  { href: '/trips', label: '여행', icon: CalendarDays },
  { href: '/files', label: '파일', icon: Paperclip },
  { href: '/notice-plans', label: '추천', icon: Newspaper },
  { href: '/trips/map-shell', label: '지도', icon: Map },
  { href: '/profile', label: '프로필', icon: UserCircle },
  { href: '/settings/mcp-tokens', label: '설정', icon: Settings },
] as const;

// 모바일 하단 탭바는 4개까지만 — 나머지는 "더보기" 행으로 접는다(320px에서 잘리지 않게).
const MOBILE_PRIMARY_HREFS = ['/', '/trips', '/notice-plans', '/trips/map-shell'] as const;
const MOBILE_PRIMARY = NAV_ITEMS.filter((item) =>
  (MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);
const MOBILE_SECONDARY = NAV_ITEMS.filter(
  (item) => !(MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  if (href === '/trips') {
    return pathname === '/trips';
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function navTestId(href: string): string {
  return `app-nav-${href.replace(/[^a-z0-9]+/gi, '-')}`;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const mobileWebLayout = useMobileWebLayout();
  const pathParts = pathname.split('/').filter(Boolean);
  const mobileTripDetail =
    mobileWebLayout &&
    pathParts.length === 2 &&
    pathParts[0] === 'trips' &&
    pathParts[1] !== 'map-shell';
  const secondaryActive = MOBILE_SECONDARY.some((item) => isActivePath(pathname, item.href));

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      {!mobileTripDetail && (
        <header className="border-b border-hairline bg-canvas">
          <div className="flex w-full items-center justify-between gap-3 px-4 py-3 md:px-6">
            <Wordmark />
            {/* 데스크톱: 가로 탭. 모바일에서는 하단 탭바가 대신하므로 숨긴다(가로 스크롤 nav 폐기). */}
            <nav className="hidden gap-1 text-sm lg:flex" aria-label="사용자 메뉴">
              {NAV_ITEMS.map((item) => {
                const active = isActivePath(pathname, item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? 'page' : undefined}
                    className={
                      // 활성 = ink 2px 밑줄(DESIGN.md product-tab), Rausch pill 아님(accent는 페이지당 1~2 moment).
                      active
                        ? 'focus-ring inline-flex min-h-11 shrink-0 items-center gap-2 rounded-sm border-b-2 border-ink px-3 font-semibold text-ink'
                        : 'focus-ring inline-flex min-h-11 shrink-0 items-center gap-2 rounded-sm border-b-2 border-transparent px-3 font-semibold text-muted hover:bg-surface-soft hover:text-ink'
                    }
                    data-testid={navTestId(item.href)}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </header>
      )}

      <main
        className={
          mobileTripDetail
            ? 'w-full flex-1'
            : 'w-full flex-1 px-4 py-6 pb-24 md:px-6 md:py-8 lg:pb-8'
        }
      >
        {children}
      </main>

      {/* 모바일 하단 탭바 — 4 + 더보기. 데스크톱(lg)에서는 상단 탭이 대신한다. */}
      {!mobileTripDetail && (
        <nav
          className="fixed inset-x-0 bottom-0 z-nav border-t border-hairline bg-canvas lg:hidden"
          aria-label="주요 메뉴"
        >
          <ul className="m-0 grid list-none grid-cols-5 p-0 pb-[env(safe-area-inset-bottom)]">
            {MOBILE_PRIMARY.map((item) => {
              const active = isActivePath(pathname, item.href);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? 'page' : undefined}
                    className={`focus-ring flex min-h-14 flex-col items-center justify-center gap-1 px-1 text-xs font-semibold ${
                      active ? 'text-ink' : 'text-muted hover:text-ink'
                    }`}
                    data-testid={`${navTestId(item.href)}-mobile`}
                  >
                    <Icon className="size-5" aria-hidden="true" />
                    <span>{item.label}</span>
                    <span
                      aria-hidden="true"
                      className={`h-0.5 w-6 rounded-full ${active ? 'bg-ink' : 'bg-transparent'}`}
                    />
                  </Link>
                </li>
              );
            })}
            <li>
              <details className="group relative" data-testid="app-nav-more">
                <summary
                  className={`focus-ring flex min-h-14 cursor-pointer list-none flex-col items-center justify-center gap-1 px-1 text-xs font-semibold marker:hidden ${
                    secondaryActive ? 'text-ink' : 'text-muted hover:text-ink'
                  }`}
                >
                  <MoreHorizontal className="size-5" aria-hidden="true" />
                  <span>더보기</span>
                  <span
                    aria-hidden="true"
                    className={`h-0.5 w-6 rounded-full ${secondaryActive ? 'bg-ink' : 'bg-transparent'}`}
                  />
                </summary>
                <ul className="absolute bottom-full right-2 mb-2 m-0 w-44 list-none rounded-md border border-hairline bg-canvas p-1 shadow-overlay">
                  {MOBILE_SECONDARY.map((item) => {
                    const active = isActivePath(pathname, item.href);
                    const Icon = item.icon;
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? 'page' : undefined}
                          className={`focus-ring flex min-h-11 items-center gap-2 rounded-sm px-3 text-sm font-semibold ${
                            active ? 'text-ink' : 'text-muted hover:bg-surface-soft hover:text-ink'
                          }`}
                          data-testid={`${navTestId(item.href)}-mobile`}
                        >
                          <Icon className="size-4" aria-hidden="true" />
                          {item.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </details>
            </li>
          </ul>
        </nav>
      )}
    </div>
  );
}
