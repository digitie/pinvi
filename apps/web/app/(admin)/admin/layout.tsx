'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { ApiClient, ApiError, authApi } from '@tripmate/api-client';
import type { AuthUser } from '@tripmate/schemas';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:8001',
});

const NAV: { href: string; label: string; sprint: number }[] = [
  { href: '/admin', label: '대시보드', sprint: 3 },
  { href: '/admin/users', label: '사용자', sprint: 3 },
  { href: '/admin/trips', label: '여행', sprint: 3 },
  { href: '/admin/features', label: '라이브러리', sprint: 3 },
  { href: '/admin/pois', label: 'POI', sprint: 3 },
  { href: '/admin/etl', label: 'ETL', sprint: 5 },
  { href: '/admin/api-calls', label: 'API 호출', sprint: 3 },
  { href: '/admin/emails', label: '이메일 큐', sprint: 3 },
  { href: '/admin/audit', label: '감사 로그', sprint: 3 },
  { href: '/admin/feature-requests', label: '요청 큐', sprint: 6 },
  { href: '/admin/category-mapping', label: '카테고리 매핑', sprint: 6 },
  { href: '/admin/seed', label: '시드 (dev)', sprint: 3 },
  { href: '/admin/reset', label: '리셋 (dev)', sprint: 3 },
];

const ADMIN_ROLES = new Set(['admin', 'operator', 'cpo']);

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<AuthUser | null>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'unauth'>('loading');

  // login 페이지 자체는 가드 적용 X (무한 redirect 방지)
  const isLoginPage = pathname === '/admin/login';

  useEffect(() => {
    if (isLoginPage) {
      setState('ok');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const user = await authApi(apiClient).me();
        if (cancelled) return;
        const hasAdmin = user.roles.some((r) => ADMIN_ROLES.has(r));
        if (!hasAdmin) {
          // 사용자 존재해도 admin role 없으면 404 자체 — login 페이지로 강제 이동
          router.replace('/admin/login?reason=forbidden');
          setState('unauth');
          return;
        }
        setMe(user);
        setState('ok');
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 404)) {
          router.replace('/admin/login');
        }
        setState('unauth');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoginPage, router]);

  if (isLoginPage) {
    return <div className="min-h-screen bg-surface-soft">{children}</div>;
  }

  if (state === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted">
        권한 확인 중...
      </div>
    );
  }
  if (state === 'unauth') {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-surface-soft">
      <aside className="w-60 shrink-0 border-r border-hairline bg-white">
        <div className="border-b border-hairline px-4 py-4">
          <Link href="/admin" className="text-sm font-bold text-ink">
            TripMate Admin
          </Link>
          {me && (
            <p className="mt-1 text-xs text-muted" data-testid="admin-me">
              {me.email}
              <br />
              <span className="text-[10px] uppercase tracking-wide">
                {me.roles.filter((r) => r !== 'user').join(', ') || 'user'}
              </span>
            </p>
          )}
        </div>
        <nav className="flex flex-col gap-1 p-2 text-sm">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? 'rounded-sm bg-primary px-3 py-2 text-white'
                    : 'rounded-sm px-3 py-2 text-ink hover:bg-surface-soft'
                }
                data-testid={`admin-nav-${item.href.replace(/[^a-z0-9]+/gi, '-')}`}
              >
                <span>{item.label}</span>
                <span className="ml-2 text-[10px] uppercase text-muted">S{item.sprint}</span>
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1 overflow-x-hidden px-8 py-8">{children}</main>
    </div>
  );
}
