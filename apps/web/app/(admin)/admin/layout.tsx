'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, authApi, queryKeys } from '@pinvi/api-client';
import {
  Activity,
  BarChart3,
  Bug,
  ChevronsLeft,
  ChevronsRight,
  GitCompare,
  GitPullRequest,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Lightbulb,
  Mail,
  MapPin,
  Paperclip,
  RefreshCw,
  RotateCcw,
  Route,
  ScrollText,
  Search,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  Sprout,
  Tags,
  UserRound,
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { AdminQueryProvider } from '@/components/admin/AdminQueryProvider';
// 좌측 메뉴 이동 중 RSC/client transition 실패가 Next 기본 오류 화면으로 새지 않도록
// document navigation으로 이동한다 (kor-travel-geo T-278 이식).
import { DocumentNavLink } from '@/components/navigation/DocumentNavLink';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const NAV_GROUPS: {
  title: string;
  items: { href: string; label: string; sprint: number; icon: LucideIcon }[];
}[] = [
  {
    title: 'Pinvi 운영',
    items: [
      { href: '/admin', label: '대시보드', sprint: 4, icon: LayoutDashboard },
      { href: '/admin/users', label: '사용자', sprint: 3, icon: Users },
      { href: '/admin/trips', label: '여행', sprint: 3, icon: Route },
      { href: '/admin/pois', label: 'POI', sprint: 3, icon: MapPin },
      { href: '/admin/files', label: '파일', sprint: 4, icon: Paperclip },
      { href: '/admin/feature-requests', label: 'Feature 제안', sprint: 4, icon: Lightbulb },
      { href: '/admin/audit', label: '감사 로그', sprint: 3, icon: ScrollText },
      { href: '/admin/incidents', label: 'Incidents', sprint: 6, icon: ShieldAlert },
    ],
  },
  {
    title: '지도 데이터',
    items: [
      { href: '/admin/features', label: 'Features', sprint: 4, icon: Search },
      {
        href: '/admin/features/change-requests',
        label: '변경 요청',
        sprint: 4,
        icon: GitPullRequest,
      },
      { href: '/admin/dedup-review', label: 'Dedup review', sprint: 5, icon: GitCompare },
      { href: '/admin/provider-sync', label: 'Provider sync', sprint: 5, icon: RefreshCw },
      { href: '/admin/integrity', label: '정합성', sprint: 5, icon: ShieldCheck },
      { href: '/admin/category-mapping', label: '카테고리 매핑', sprint: 6, icon: Tags },
      { href: '/admin/debug/logs', label: 'Debug logs', sprint: 5, icon: Bug },
    ],
  },
  {
    title: '시스템 운영',
    items: [
      { href: '/admin/system', label: '시스템', sprint: 5, icon: ServerCog },
      { href: '/admin/etl', label: 'ETL', sprint: 5, icon: Workflow },
      { href: '/admin/grafana', label: 'Grafana', sprint: 5, icon: BarChart3 },
      { href: '/admin/api-calls', label: 'API 호출', sprint: 3, icon: Activity },
      { href: '/admin/emails', label: '이메일 큐', sprint: 3, icon: Mail },
      { href: '/admin/backup', label: 'Backup', sprint: 5, icon: HardDrive },
      { href: '/admin/mcp-tokens', label: 'MCP 토큰', sprint: 6, icon: KeyRound },
      { href: '/admin/seed', label: '시드 (dev)', sprint: 3, icon: Sprout },
      { href: '/admin/reset', label: '리셋 (dev)', sprint: 3, icon: RotateCcw },
    ],
  },
];
const NAV_HREFS = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.href));

const ADMIN_ROLES = new Set(['admin', 'operator', 'cpo']);
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'pinvi.admin.sidebar.collapsed';

function getActiveNavHref(pathname: string) {
  const matches = NAV_HREFS.filter((href) =>
    href === '/admin' ? pathname === href : pathname === href || pathname.startsWith(`${href}/`),
  );
  return matches.sort((a, b) => b.length - a.length)[0] ?? null;
}

/** 권한 가드 + 사이드바 — Query provider 내부에서 me()를 useQuery로 확인한다. */
function AdminGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarPreferenceReady, setSidebarPreferenceReady] = useState(false);
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
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    setSidebarCollapsed(stored === '1');
    setSidebarPreferenceReady(true);
  }, []);

  useEffect(() => {
    if (!sidebarPreferenceReady) return;
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed ? '1' : '0');
  }, [sidebarCollapsed, sidebarPreferenceReady]);

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
  const activeHref = getActiveNavHref(pathname);

  return (
    <div className="flex min-h-screen flex-col bg-surface-soft lg:flex-row">
      <aside
        className={`shrink-0 border-b border-hairline bg-white transition-[width] duration-200 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r ${
          sidebarCollapsed ? 'lg:w-20' : 'lg:w-64'
        }`}
        data-collapsed={sidebarCollapsed ? 'true' : 'false'}
        data-testid="admin-sidebar"
      >
        <div
          className={`flex items-center gap-2 border-b border-hairline px-2 py-3 ${
            sidebarCollapsed ? 'lg:flex-col' : 'lg:px-4'
          }`}
        >
          <DocumentNavLink
            href="/admin"
            aria-label="Pinvi Admin"
            title="Pinvi Admin"
            className="flex h-11 w-11 items-center justify-center rounded-sm bg-ink text-sm font-bold text-white"
          >
            PA
          </DocumentNavLink>
          {!sidebarCollapsed && (
            <div className="hidden min-w-0 flex-1 lg:block">
              <p className="truncate text-sm font-semibold text-ink">Pinvi Admin</p>
              <p className="truncate text-xs text-muted">
                {me.roles.filter((r) => r !== 'user').join(', ') || 'user'}
              </p>
            </div>
          )}
          <button
            type="button"
            aria-label={sidebarCollapsed ? 'Admin 메뉴 펼치기' : 'Admin 메뉴 접기'}
            title={sidebarCollapsed ? 'Admin 메뉴 펼치기' : 'Admin 메뉴 접기'}
            aria-pressed={sidebarCollapsed}
            data-testid="admin-sidebar-toggle"
            className="hidden h-9 w-9 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary lg:flex"
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            {sidebarCollapsed ? (
              <ChevronsRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          <div
            className="flex h-11 w-11 items-center justify-center rounded-sm border border-hairline text-muted"
            data-testid="admin-me"
            title={`${me.email} / ${me.roles.filter((r) => r !== 'user').join(', ') || 'user'}`}
            aria-label={`로그인 사용자 ${me.email}`}
          >
            <UserRound className="h-5 w-5" aria-hidden="true" />
          </div>
        </div>
        <nav
          className={`flex gap-2 overflow-x-auto p-2 text-sm lg:block lg:overflow-x-visible ${
            sidebarCollapsed ? 'lg:space-y-3' : 'lg:space-y-5 lg:p-3'
          }`}
          aria-label="Admin navigation"
        >
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className="flex gap-1 lg:block lg:space-y-1">
              <h2
                className={
                  sidebarCollapsed
                    ? 'sr-only'
                    : 'sr-only lg:not-sr-only lg:mb-2 lg:block lg:px-2 lg:text-xs lg:font-semibold lg:text-muted'
                }
              >
                {group.title}
              </h2>
              <div
                aria-hidden="true"
                className={
                  sidebarCollapsed
                    ? 'hidden lg:mx-auto lg:mb-2 lg:block lg:h-px lg:w-8 lg:bg-hairline'
                    : 'hidden'
                }
              />
              <div className="flex gap-1 lg:grid lg:grid-cols-1">
                {group.items.map((item) => {
                  const active = activeHref === item.href;
                  const Icon = item.icon;
                  const linkSize = sidebarCollapsed
                    ? 'h-11 w-11 justify-center'
                    : 'h-11 w-11 justify-center lg:h-10 lg:w-full lg:justify-start lg:gap-2 lg:px-3';
                  const labelClass = sidebarCollapsed
                    ? 'sr-only'
                    : 'sr-only lg:not-sr-only lg:block lg:min-w-0 lg:flex-1 lg:truncate';
                  return (
                    <DocumentNavLink
                      key={item.href}
                      href={item.href}
                      aria-label={`${item.label} (Sprint ${item.sprint})`}
                      aria-current={active ? 'page' : undefined}
                      title={`${item.label} (Sprint ${item.sprint})`}
                      data-sprint={item.sprint}
                      className={
                        active
                          ? `flex ${linkSize} rounded-sm bg-primary text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`
                          : `flex ${linkSize} rounded-sm text-ink hover:bg-surface-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary`
                      }
                      data-testid={`admin-nav-${item.href.replace(/[^a-z0-9]+/gi, '-')}`}
                    >
                      <Icon className="h-5 w-5" aria-hidden="true" />
                      <span className={labelClass}>{item.label}</span>
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
