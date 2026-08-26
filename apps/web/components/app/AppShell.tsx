'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
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
  { href: '/trips', label: '여행', icon: CalendarDays },
  { href: '/notice-plans', label: '추천', icon: Newspaper },
  // '지도' = 실제 탐색 지도(/map). `/trips/map-shell`은 VWorld 렌더 스모크용 데모 셸이라
  // nav에 걸지 않는다 — 걸어 두면 하드코딩 데모가 주 목적지가 되고 진짜 지도는 도달 불가였다(T-316).
  { href: '/map', label: '지도', icon: Map },
  { href: '/files', label: '파일', icon: Paperclip },
  { href: '/settings/mcp-tokens', label: '설정', icon: Settings },
  { href: '/profile', label: '프로필', icon: UserCircle },
  { href: '/', label: '홈', icon: LayoutDashboard },
] as const;

// 모바일 하단 탭바 1순위 = **앱 셸 안에 머무는** 목적지 4개.
// `/`·`/profile`은 셸 밖(마케팅 랜딩 / auth 레이아웃)이라 탭바가 사라지므로 더보기 시트로 내린다(T-314 리뷰 P2/P3).
const MOBILE_PRIMARY_HREFS = ['/trips', '/notice-plans', '/map', '/files'] as const;
const MOBILE_PRIMARY = NAV_ITEMS.filter((item) =>
  (MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);
const MOBILE_SECONDARY = NAV_ITEMS.filter(
  (item) => !(MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);
// 셸 밖으로 나가는 목적지 — 접근성 이름에 이동 사실을 명시한다.
const LEAVES_APP_SHELL: readonly string[] = ['/', '/profile'];

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  if (href === '/trips') {
    return pathname === '/trips';
  }
  if (href.startsWith('/settings')) {
    // /settings/* 전체를 "설정" 탭으로 묶는다(consents·telegram·dsr·moderation 포함).
    return pathname === '/settings' || pathname.startsWith('/settings/');
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function navTestId(href: string): string {
  return `app-nav-${href.replace(/[^a-z0-9]+/gi, '-')}`;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const mobileWebLayout = useMobileWebLayout();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLLIElement>(null);
  const moreSheetId = useId();
  const pathParts = pathname.split('/').filter(Boolean);
  const mobileTripDetail =
    mobileWebLayout &&
    pathParts.length === 2 &&
    pathParts[0] === 'trips' &&
    pathParts[1] !== 'map-shell';
  const secondaryActive = MOBILE_SECONDARY.some((item) => isActivePath(pathname, item.href));

  // 라우트가 바뀌면 시트를 닫는다 — 네이티브 <details>는 클라이언트 네비게이션 후에도 열린 채 남았다.
  // effect 대신 렌더 중 조정(react-hooks/set-state-in-effect가 막는 effect 내부 동기 setState를 피한다).
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setMoreOpen(false);
  }

  // 바깥 포인터·포커스 이탈·Escape로도 닫는다(브라우저 기본 동작에 기대지 않는다).
  useEffect(() => {
    if (!moreOpen) return;
    const closeIfOutside = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && moreRef.current?.contains(target)) return;
      setMoreOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMoreOpen(false);
    };
    document.addEventListener('pointerdown', closeIfOutside);
    document.addEventListener('focusin', closeIfOutside);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', closeIfOutside);
      document.removeEventListener('focusin', closeIfOutside);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [moreOpen]);

  return (
    <div
      className="flex min-h-dvh flex-col bg-canvas"
      // 셸의 모바일/데스크톱 전환은 CSS(lg)가 1차, 이 속성이 넓은 layout viewport를 쓰는 폰을 보정한다.
      data-mobile-layout={mobileWebLayout ? 'on' : 'off'}
    >
      {!mobileTripDetail && (
        <header className="border-b border-hairline bg-canvas">
          <div className="flex w-full items-center justify-between gap-3 px-4 py-3 md:px-6">
            <Wordmark />
            {/* 데스크톱: 가로 탭. 모바일에서는 하단 탭바가 대신하므로 숨긴다(가로 스크롤 nav 폐기). */}
            <nav
              className="app-shell-desktop-nav hidden gap-1 text-sm lg:flex"
              aria-label="사용자 메뉴"
            >
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
            ? 'flex min-h-0 w-full flex-1 flex-col'
            : // 하단 패딩은 `.app-shell-main`이 소유한다 — `py-*` 유틸과 겹치면 md 변형이 이를 덮어
              // 768~1023px에서 고정 탭바가 콘텐츠를 가린다(T-314 리뷰 P1).
              'app-shell-main flex min-h-0 w-full flex-1 flex-col px-4 pt-6 md:px-6 md:pt-8'
        }
      >
        {children}
      </main>

      {/* 모바일 하단 탭바 — 4 + 더보기. 데스크톱(lg)에서는 상단 탭이 대신한다. */}
      {!mobileTripDetail && (
        <nav
          className="app-shell-tabbar fixed inset-x-0 bottom-0 z-nav border-t border-hairline bg-canvas lg:hidden"
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
            <li className="relative" ref={moreRef} data-testid="app-nav-more">
              {/* details/summary는 display:flex를 주면 Blink가 disclosure 시맨틱을 잃는다 —
                  button + aria-expanded/aria-controls로 상태를 직접 노출한다(T-314 리뷰 P2). */}
              <button
                type="button"
                aria-expanded={moreOpen}
                aria-controls={moreSheetId}
                onClick={() => setMoreOpen((open) => !open)}
                className={`focus-ring flex min-h-14 w-full flex-col items-center justify-center gap-1 px-1 text-xs font-semibold ${
                  secondaryActive ? 'text-ink' : 'text-muted hover:text-ink'
                }`}
                data-testid="app-nav-more-toggle"
              >
                <MoreHorizontal className="size-5" aria-hidden="true" />
                <span>
                  더보기
                  {secondaryActive ? <span className="sr-only"> (현재 위치 포함)</span> : null}
                </span>
                <span
                  aria-hidden="true"
                  className={`h-0.5 w-6 rounded-full ${secondaryActive ? 'bg-ink' : 'bg-transparent'}`}
                />
              </button>
              {moreOpen && (
                <ul
                  id={moreSheetId}
                  className="absolute bottom-full right-2 m-0 mb-2 w-48 list-none rounded-md border border-hairline bg-canvas p-1 shadow-overlay"
                >
                  {MOBILE_SECONDARY.map((item) => {
                    const active = isActivePath(pathname, item.href);
                    const Icon = item.icon;
                    const leaves = LEAVES_APP_SHELL.includes(item.href);
                    return (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          aria-current={active ? 'page' : undefined}
                          onClick={() => setMoreOpen(false)}
                          className={`focus-ring flex min-h-11 items-center gap-2 rounded-sm px-3 text-sm font-semibold ${
                            active ? 'text-ink' : 'text-muted hover:bg-surface-soft hover:text-ink'
                          }`}
                          data-testid={`${navTestId(item.href)}-mobile`}
                        >
                          <Icon className="size-4" aria-hidden="true" />
                          {item.label}
                          {leaves ? <span className="sr-only">(앱 메뉴 밖으로 이동)</span> : null}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          </ul>
        </nav>
      )}
    </div>
  );
}
