'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import {
  CalendarDays,
  LayoutDashboard,
  Map,
  Newspaper,
  Paperclip,
  Settings,
  UserCircle,
} from 'lucide-react';
import { useMobileWebLayout } from '@/lib/useMobileWebLayout';
import { Wordmark } from '@/components/app/Wordmark';

const NAV_ITEMS = [
  { href: '/', label: '홈', icon: LayoutDashboard },
  { href: '/trips', label: '여행', icon: CalendarDays },
  { href: '/files', label: '파일', icon: Paperclip },
  { href: '/notice-plans', label: '추천', icon: Newspaper },
  { href: '/trips/map-shell', label: '지도', icon: Map },
  { href: '/profile', label: '프로필', icon: UserCircle },
  { href: '/settings/mcp-tokens', label: '설정', icon: Settings },
] as const;

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }
  if (href === '/trips') {
    return pathname === '/trips';
  }
  return pathname === href || pathname.startsWith(`${href}/`);
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

  return (
    <div className="min-h-dvh bg-surface-soft">
      {!mobileTripDetail && (
        <header className="border-b border-hairline bg-canvas">
          <div className="flex w-full flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6">
            <Wordmark />
            <nav className="flex gap-1 overflow-x-auto text-sm" aria-label="사용자 메뉴">
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
                    data-testid={`app-nav-${item.href.replace(/[^a-z0-9]+/gi, '-')}`}
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
      <main className={mobileTripDetail ? 'w-full' : 'w-full px-4 py-6 md:px-6 md:py-8'}>
        {children}
      </main>
    </div>
  );
}
