'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

const TABS = [
  { href: '/settings/consents', label: '동의 관리' },
  { href: '/settings/dsr', label: '개인정보 요청' },
  { href: '/settings/mcp-tokens', label: 'MCP 토큰' },
  { href: '/settings/telegram', label: 'Telegram 알림' },
] as const;

export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      <nav
        className="flex gap-1 overflow-x-auto border-b border-hairline pb-2 text-sm"
        aria-label="설정 메뉴"
      >
        {TABS.map((tab) => {
          const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={
                active
                  ? 'h-9 shrink-0 rounded-sm bg-ink px-3 leading-9 font-semibold text-white'
                  : 'h-9 shrink-0 rounded-sm px-3 leading-9 font-semibold text-ink hover:bg-surface-soft'
              }
              data-testid={`settings-tab-${tab.href.split('/').pop()}`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
