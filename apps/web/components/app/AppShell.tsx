'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import {
  CalendarDays,
  Compass,
  LayoutDashboard,
  Map,
  Newspaper,
  Paperclip,
  Settings,
  UserCircle,
} from 'lucide-react';

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

  return (
    <div className="min-h-screen bg-surface-soft">
      <header className="border-b border-hairline bg-white">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6">
          <Link href="/" className="inline-flex items-center gap-2 text-sm font-bold text-ink">
            <Compass className="h-5 w-5 text-primary" aria-hidden="true" />
            Pinvi
          </Link>
          <nav className="flex gap-1 overflow-x-auto text-sm" aria-label="사용자 메뉴">
            {NAV_ITEMS.map((item) => {
              const active = isActivePath(pathname, item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={
                    active
                      ? 'inline-flex h-10 shrink-0 items-center gap-2 rounded-sm bg-primary px-3 font-semibold text-white'
                      : 'inline-flex h-10 shrink-0 items-center gap-2 rounded-sm px-3 font-semibold text-ink hover:bg-surface-soft'
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
      <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-8">{children}</main>
    </div>
  );
}
