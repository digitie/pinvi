'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, authApi, queryKeys } from '@pinvi/api-client';
import { AdminQueryProvider } from '@/components/admin/AdminQueryProvider';
// 좌측 메뉴 이동 중 RSC/client transition 실패가 Next 기본 오류 화면으로 새지 않도록
// document navigation으로 이동한다 (kor-travel-geo T-278 이식).
import { DocumentNavLink } from '@/components/navigation/DocumentNavLink';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const NAV_GROUPS: {
  title: string;
  items: { href: string; label: string; sprint: number }[];
}[] = [
  {
    title: 'Pinvi 운영',
    items: [
      { href: '/admin', label: '대시보드', sprint: 4 },
      { href: '/admin/users', label: '사용자', sprint: 3 },
      { href: '/admin/trips', label: '여행', sprint: 3 },
      { href: '/admin/pois', label: 'POI', sprint: 3 },
      { href: '/admin/feature-requests', label: 'Feature 제안', sprint: 4 },
      { href: '/admin/audit', label: '감사 로그', sprint: 3 },
    ],
  },
  {
    title: '지도 데이터',
    items: [
      { href: '/admin/features', label: 'Features', sprint: 4 },
      { href: '/admin/features/change-requests', label: '변경 요청', sprint: 4 },
      { href: '/admin/dedup-review', label: 'Dedup review', sprint: 5 },
      { href: '/admin/provider-sync', label: 'Provider sync', sprint: 5 },
      { href: '/admin/integrity', label: '정합성', sprint: 5 },
      { href: '/admin/category-mapping', label: '카테고리 매핑', sprint: 6 },
      { href: '/admin/debug/logs', label: 'Debug logs', sprint: 5 },
    ],
  },
  {
    title: '시스템 운영',
    items: [
      { href: '/admin/etl', label: 'ETL', sprint: 5 },
      { href: '/admin/grafana', label: 'Grafana', sprint: 5 },
      { href: '/admin/api-calls', label: 'API 호출', sprint: 3 },
      { href: '/admin/emails', label: '이메일 큐', sprint: 3 },
      { href: '/admin/backup', label: 'Backup', sprint: 5 },
      { href: '/admin/mcp-tokens', label: 'MCP 토큰', sprint: 6 },
      { href: '/admin/seed', label: '시드 (dev)', sprint: 3 },
      { href: '/admin/reset', label: '리셋 (dev)', sprint: 3 },
    ],
  },
];
const NAV_HREFS = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href));

const ADMIN_ROLES = new Set(['admin', 'operator', 'cpo']);

function isNavItemActive(pathname: string, href: string) {
  if (href === '/admin') {
    return pathname === '/admin';
  }
  if (pathname === href) {
    return true;
  }
  if (!pathname.startsWith(`${href}/`)) {
    return false;
  }
  return !NAV_HREFS.some(
    (otherHref) =>
      otherHref !== href &&
      otherHref.startsWith(`${href}/`) &&
      (pathname === otherHref || pathname.startsWith(`${otherHref}/`)),
  );
}

/** 권한 가드 + 사이드바 — Query provider 내부에서 me()를 useQuery로 확인한다. */
function AdminGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  // login 페이지 자체는 가드 적용 X (무한 redirect 방지)
  const isLoginPage = pathname === '/admin/login';

  const meQuery = useQuery({
    queryKey: queryKeys.admin.me(),
    queryFn: () => authApi(apiClient).me(),
    enabled: !isLoginPage,
    retry: false,
    staleTime: 60_000,
  });

  const me = meQuery.data ?? null;
  const hasAdmin = me ? me.roles.some((r) => ADMIN_ROLES.has(r)) : false;

  useEffect(() => {
    if (isLoginPage) return;
    if (meQuery.isError) {
      const err = meQuery.error;
      if (err instanceof ApiError && (err.status === 401 || err.status === 404)) {
        router.replace('/admin/login');
      }
      return;
    }
    if (meQuery.isSuccess && me && !hasAdmin) {
      // 사용자 존재해도 admin role 없으면 login으로 강제 이동
      router.replace('/admin/login?reason=forbidden');
    }
  }, [isLoginPage, meQuery.isError, meQuery.isSuccess, meQuery.error, me, hasAdmin, router]);

  if (isLoginPage) {
    return <div className="min-h-screen bg-surface-soft">{children}</div>;
  }
  if (meQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted">
        권한 확인 중...
      </div>
    );
  }
  if (meQuery.isError || !me || !hasAdmin) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col bg-surface-soft lg:flex-row">
      <aside className="shrink-0 border-b border-hairline bg-white lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="border-b border-hairline px-4 py-4">
          <DocumentNavLink href="/admin" className="text-sm font-bold text-ink">
            Pinvi Admin
          </DocumentNavLink>
          <p className="mt-1 text-xs text-muted" data-testid="admin-me">
            {me.email}
            <br />
            <span className="text-[10px] uppercase tracking-wide">
              {me.roles.filter((r) => r !== 'user').join(', ') || 'user'}
            </span>
          </p>
        </div>
        <nav className="space-y-4 p-2 text-sm">
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="space-y-1">
              <h2 className="px-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                {group.title}
              </h2>
              <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-1">
                {group.items.map((item) => {
                  const active = isNavItemActive(pathname, item.href);
                  return (
                    <DocumentNavLink
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
                      <span
                        className={
                          active
                            ? 'ml-2 text-[10px] uppercase text-white/75'
                            : 'ml-2 text-[10px] uppercase text-muted'
                        }
                      >
                        S{item.sprint}
                      </span>
                    </DocumentNavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-x-hidden px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
    </div>
  );
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <AdminQueryProvider>
      <AdminGuard>{children}</AdminGuard>
    </AdminQueryProvider>
  );
}
