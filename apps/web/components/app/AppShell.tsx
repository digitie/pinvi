'use client';

import { Popover, PopoverContent, PopoverTrigger } from '@kor-travel/ui/popover';
import { SkipToContentLink } from '@/components/app/SkipToContentLink';
import { Wordmark } from '@/components/app/Wordmark';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';
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
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useId, useState, type ReactNode } from 'react';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md · designed-as-app
 * nav: 데스크톱 = ink 밑줄 탭(활성 1개) · 모바일 = 하단 탭바 4 + 더보기 시트 · footer: 없음(앱 셸)
 * ground: bg-canvas(회색 ground 위 흰 카드 남발 폐기, T-314)
 */
const NAV_ITEMS = [
  // '홈' = 로그인 사용자의 개인 홈(/home, 셸 안) — 로그인 기본 목적지이자 첫 탭.
  { href: '/home', label: '홈', icon: LayoutDashboard },
  { href: '/trips', label: '여행', icon: CalendarDays },
  { href: '/notice-plans', label: '추천', icon: Newspaper },
  // '지도' = 실제 탐색 지도(/map). `/trips/map-shell`은 VWorld 렌더 스모크용 데모 셸이라
  // nav에 걸지 않는다 — 걸어 두면 하드코딩 데모가 주 목적지가 되고 진짜 지도는 도달 불가였다(T-316).
  { href: '/map', label: '지도', icon: Map },
  { href: '/files', label: '파일', icon: Paperclip },
  { href: '/settings/mcp-tokens', label: '설정', icon: Settings },
  { href: '/profile', label: '프로필', icon: UserCircle },
] as const;

// 모바일 하단 탭바 1순위 = **앱 셸 안에 머무는** 목적지 4개 + 더보기 = 5칸(320px에서 칸당 64px, 높이 56px).
// 홈이 첫 탭이고, 파일은 더보기로 내렸다(2026-11-17 소유자 결정).
// `/profile`은 셸 밖(auth 레이아웃)이라 탭바가 사라지므로 더보기 시트로 내린다(T-314 리뷰 P2/P3).
const MOBILE_PRIMARY_HREFS = ['/home', '/trips', '/notice-plans', '/map'] as const;
const MOBILE_PRIMARY = NAV_ITEMS.filter((item) =>
  (MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);
const MOBILE_SECONDARY = NAV_ITEMS.filter(
  (item) => !(MOBILE_PRIMARY_HREFS as readonly string[]).includes(item.href),
);
// 셸 밖으로 나가는 목적지 — 접근성 이름에 이동 사실을 명시한다.
const LEAVES_APP_SHELL: readonly string[] = ['/profile'];

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/trips') {
    return pathname === '/trips' || pathname === '/trips/trash';
  }
  if (href.startsWith('/settings')) {
    // /settings/* 전체를 "설정" 탭으로 묶는다(consents·telegram·dsr·moderation 포함).
    return pathname === '/settings' || pathname.startsWith('/settings/');
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

interface ShellLayoutClasses {
  root: string;
  header: string;
  headerRow: string;
  main: string;
}

/**
 * 셸 상자들의 class — 경로 종류(전체 화면 탐색 지도 / 데스크톱·모바일 여행 상세 / 일반)마다 한 곳에서 고른다.
 *
 * - 탐색 지도(`/map`, 소유자 요청 2026-11-17 "지도도 전체화면으로"): 창 높이 고정·스크롤 없음, 본문 여백 없음(하단 패딩은
 *   `.app-shell-main-map`이 모바일 탭바 높이만), 상단 바는 데스크톱만 얇게(`py-1`)·모바일은 숨김(CSS 1차라 SSR 첫 페인트도 같다).
 * - 데스크톱 여행 상세: 창 높이에 고정한다 — 셸이 min-h-dvh로 자라면 왼쪽 패널 내용만큼 지도 열도 자라 900px 창에서
 *   지도가 ~1590px가 되고 핀이 fold 아래에 그려졌다(#704). lg: 접두는 SSR 첫 페인트(mobileWebLayout=false)에서 좁은
 *   화면의 페이지 스크롤을 막지 않게 한다. 바닥(min-h)보다 낮은 창에서는 잘라내지 않고 문서가 스크롤된다.
 * - 일반 본문: 하단 패딩은 `.app-shell-main`이 소유한다 — `py-*` 유틸과 겹치면 md 변형이 이를 덮어 768~1023px에서
 *   고정 탭바가 콘텐츠를 가린다(T-314 리뷰 P1).
 */
function shellLayoutClasses(route: {
  exploreMap: boolean;
  desktopTripDetail: boolean;
  mobileTripDetail: boolean;
}): ShellLayoutClasses {
  const header = 'border-b border-hairline bg-canvas';
  const headerRow = 'flex w-full items-center justify-between gap-3 px-4 md:px-6';
  const main = 'flex min-h-0 w-full flex-1 flex-col';
  if (route.exploreMap) {
    return {
      root: 'flex h-dvh flex-col overflow-hidden bg-canvas',
      header: `app-shell-map-header hidden shrink-0 lg:block ${header}`,
      headerRow: `${headerRow} py-1`,
      main: `app-shell-main-map ${main}`,
    };
  }
  return {
    root: route.desktopTripDetail
      ? 'flex min-h-dvh flex-col bg-canvas lg:h-dvh lg:min-h-[560px]'
      : 'flex min-h-dvh flex-col bg-canvas',
    header,
    headerRow: `${headerRow} py-3`,
    main: route.mobileTripDetail ? main : `app-shell-main ${main} px-4 pt-6 md:px-6 md:pt-8`,
  };
}

/** 전체 화면 지도 셸을 쓰는 경로 — 탐색 지도 `/map` 하나(하위 경로 없음). */
function isExploreMapPath(pathname: string): boolean {
  return pathname === '/map' || pathname === '/map/';
}

function navTestId(href: string): string {
  return `app-nav-${href.replace(/[^a-z0-9]+/gi, '-')}`;
}

export function AppShell(...args: Parameters<typeof useAppShellModel>) {
  const viewModel = useAppShellModel(...args);
  if (viewModel.renderBranch === 'render0') return <AppShellView0 viewModel={viewModel} />;
  return null;
}

function useAppShellModel({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const mobileWebLayout = useMobileWebLayout();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreSheetId = useId();
  const pathParts = pathname.split('/').filter(Boolean);
  const tripDetailRoute =
    pathParts.length === 2 &&
    pathParts[0] === 'trips' &&
    pathParts[1] !== 'map-shell' &&
    pathParts[1] !== 'trash';
  const mobileTripDetail = mobileWebLayout && tripDetailRoute;
  // 데스크톱 여행 상세는 창 높이에 고정한다(#704) — class 근거는 `shellLayoutClasses`.
  const desktopTripDetail = !mobileWebLayout && tripDetailRoute;
  // 탐색 지도(/map)는 전체 화면 지도다(소유자 요청 2026-11-17 "지도도 전체화면으로").
  const exploreMapRoute = isExploreMapPath(pathname);
  const layout = shellLayoutClasses({
    exploreMap: exploreMapRoute,
    desktopTripDetail,
    mobileTripDetail,
  });
  const secondaryActive = MOBILE_SECONDARY.some((item) => isActivePath(pathname, item.href));

  // 라우트가 바뀌면 시트를 닫는다 — 네이티브 <details>는 클라이언트 네비게이션 후에도 열린 채 남았다.
  // effect 대신 렌더 중 조정(react-hooks/set-state-in-effect가 막는 effect 내부 동기 setState를 피한다).
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setMoreOpen(false);
  }

  return {
    renderBranch: 'render0' as const,
    children,
    exploreMapRoute,
    layout,
    mobileTripDetail,
    mobileWebLayout,
    moreOpen,
    moreSheetId,
    pathname,
    secondaryActive,
    setMoreOpen,
  };
}

type AppShellView0Model = Extract<ReturnType<typeof useAppShellModel>, { renderBranch: 'render0' }>;
function AppShellView0({ viewModel }: { viewModel: AppShellView0Model }) {
  const {
    children,
    exploreMapRoute,
    layout,
    mobileTripDetail,
    mobileWebLayout,
    moreOpen,
    moreSheetId,
    pathname,
    secondaryActive,
    setMoreOpen,
  } = viewModel;
  return (
    <div
      className={layout.root}
      data-explore-map={exploreMapRoute ? 'on' : undefined}
      // 셸의 모바일/데스크톱 전환은 CSS(lg)가 1차, 이 속성이 넓은 layout viewport를 쓰는 폰을 보정한다.
      data-mobile-layout={mobileWebLayout ? 'on' : 'off'}
    >
      <SkipToContentLink />
      {!mobileTripDetail && (
        <header className={layout.header}>
          <div className={layout.headerRow}>
            {/* 로고 = 개인 홈. 로그인하지 않았으면 /home의 401이 로그인 화면으로 보낸다. */}
            <Wordmark href="/home" />
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

      <main id="main" tabIndex={-1} className={layout.main}>
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
            <li className="relative" data-testid="app-nav-more">
              <Popover open={moreOpen && mobileWebLayout} onOpenChange={setMoreOpen}>
                <PopoverTrigger asChild>
                  {/* details/summary는 display:flex를 주면 Blink가 disclosure 시맨틱을 잃는다 —
                  button + aria-expanded/aria-controls로 상태를 직접 노출한다(T-314 리뷰 P2). */}
                  <button
                    type="button"
                    aria-expanded={moreOpen}
                    aria-controls={moreSheetId}
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
                </PopoverTrigger>
                <PopoverContent
                  id={moreSheetId}
                  aria-label="더보기 메뉴"
                  side="top"
                  align="end"
                  alignOffset={8}
                  sideOffset={8}
                  onOpenAutoFocus={(event) => event.preventDefault()}
                  className="z-panel block w-48 rounded-md border border-hairline bg-canvas p-1 text-ink shadow-overlay ring-0"
                >
                  <ul className="m-0 list-none p-0">
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
                              active
                                ? 'text-ink'
                                : 'text-muted hover:bg-surface-soft hover:text-ink'
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
                </PopoverContent>
              </Popover>
            </li>
          </ul>
        </nav>
      )}
    </div>
  );
}
