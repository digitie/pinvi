'use client';

import { AppMenu, type AppMenuGroup, type AppMenuLinkProps } from '@kor-travel/ui';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, authApi, queryKeys } from '@pinvi/api-client';
import {
  Activity,
  Archive,
  Ban,
  BarChart3,
  Bug,
  ChevronsLeft,
  ChevronsRight,
  ClipboardCheck,
  GitCompare,
  Gavel,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Lightbulb,
  Mail,
  MapPin,
  Newspaper,
  Paperclip,
  RefreshCw,
  RotateCcw,
  Route,
  ScrollText,
  Search,
  ServerCog,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sprout,
  Tags,
  UserRound,
  LogOut,
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { ADMIN_MAIN_CONTENT_ID, AdminSkipLink } from '@/components/admin/admin-shell-parts';
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
      { href: '/admin/rbac', label: 'RBAC', sprint: 6, icon: Shield },
      { href: '/admin/trips', label: '여행', sprint: 3, icon: Route },
      { href: '/admin/pois', label: 'POI', sprint: 3, icon: MapPin },
      { href: '/admin/notice-plans', label: '추천 여행', sprint: 6, icon: Newspaper },
      { href: '/admin/files', label: '파일', sprint: 4, icon: Paperclip },
      { href: '/admin/feature-requests', label: 'Feature 제안', sprint: 4, icon: Lightbulb },
      {
        href: '/admin/feature-reference-reconciliations',
        label: '참조 조정 증거',
        sprint: 5,
        icon: GitCompare,
      },
      { href: '/admin/audit', label: '감사 로그', sprint: 3, icon: ScrollText },
      { href: '/admin/incidents', label: 'Incidents', sprint: 6, icon: ShieldAlert },
      { href: '/admin/abuse', label: 'Abuse', sprint: 6, icon: Ban },
      { href: '/admin/dsr', label: 'DSR', sprint: 6, icon: ClipboardCheck },
      { href: '/admin/moderation', label: 'Moderation', sprint: 6, icon: Gavel },
    ],
  },
  {
    title: '지도 데이터',
    items: [
      { href: '/admin/features', label: 'Features', sprint: 4, icon: Search },
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
      { href: '/admin/retention', label: 'Retention', sprint: 6, icon: Archive },
      { href: '/admin/seed', label: '시드 (dev)', sprint: 3, icon: Sprout },
      { href: '/admin/reset', label: '리셋 (dev)', sprint: 3, icon: RotateCcw },
    ],
  },
];
const ADMIN_ROLES = new Set(['admin', 'operator', 'cpo']);
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'pinvi.admin.sidebar.collapsed';
const COMMON_MENU_GROUPS: AppMenuGroup[] = NAV_GROUPS.map((group) => ({
  id: group.title,
  label: group.title,
  items: group.items.map((item) => ({
    id: item.href,
    href: item.href,
    label: item.label,
    exact: item.href === '/admin',
    icon: <item.icon className="size-4" aria-hidden="true" />,
  })),
}));
function CommonDocumentLink({ href, children, ...props }: AppMenuLinkProps) {
  return (
    <a href={href} {...props} data-testid={`admin-nav-${href.replace(/[^a-z0-9]+/gi, '-')}`}>
      {children}
    </a>
  );
}

/** 권한 가드 + 사이드바 — Query provider 내부에서 me()를 useQuery로 확인한다. */
function AdminGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const pathname = usePathname();
  // 최초 렌더에서 lazy initializer로 한 번만 읽는다 — sidebar 마크업은 meQuery가
  // pending인 동안(SSR·hydration 포함) 렌더되지 않으므로 여기서 window 접근이 안전하다.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === '1',
  );
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
    window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed ? '1' : '0');
  }, [sidebarCollapsed]);

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

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await authApi(apiClient).logout();
      queryClient.clear();
      router.replace('/admin/login');
    } catch {
      setLogoutError('로그아웃하지 못했습니다. 다시 시도해 주세요.');
      setLoggingOut(false);
    }
  }

  if (isLoginPage) {
    return <div className="min-h-dvh bg-surface-soft">{children}</div>;
  }
  if (meQuery.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center text-sm text-muted">
        권한 확인 중…
      </div>
    );
  }
  if (meQuery.isError) {
    return (
      <div className="p-8" role="alert">
        권한을 확인하지 못했습니다.
        <button type="button" onClick={() => void meQuery.refetch()} className="ml-3 underline">
          다시 확인
        </button>
      </div>
    );
  }
  if (!me || !hasAdmin) return null;

  return (
    <div className="pinvi-admin-shell flex min-h-dvh min-w-0 max-w-full flex-col overflow-x-clip bg-canvas lg:flex-row">
      {/* 좌측 rail은 nav 항목이 30개가 넘는다 — 키보드/스크린리더 사용자가 매 페이지마다 그걸
          전부 통과하지 않도록 본문 건너뛰기를 nav 앞에 둔다(kor-travel-map admin 규약, T-356). */}
      <AdminSkipLink />
      <aside
        className={`flex w-full max-w-[100dvw] min-w-0 shrink-0 flex-col border-b border-admin-line bg-canvas transition-[width] duration-200 lg:sticky lg:top-0 lg:h-dvh lg:border-b-0 lg:border-r ${
          sidebarCollapsed ? 'lg:w-16' : 'lg:w-64'
        }`}
        data-collapsed={sidebarCollapsed ? 'true' : 'false'}
        data-testid="admin-sidebar"
      >
        <div
          className={`flex h-14 shrink-0 items-center justify-between gap-2 border-b border-admin-line px-3 ${sidebarCollapsed ? 'lg:h-auto lg:flex-col lg:py-2' : ''}`}
        >
          <DocumentNavLink
            href="/admin"
            aria-label="Pinvi Admin"
            className="flex min-w-0 items-baseline gap-2 text-sm font-semibold tracking-tight text-ink"
          >
            <span className={sidebarCollapsed ? 'lg:hidden' : ''}>Pinvi</span>
            <span
              className={sidebarCollapsed ? 'text-xs text-muted lg:hidden' : 'text-xs text-muted'}
            >
              admin
            </span>
            <span aria-hidden="true" className={sidebarCollapsed ? 'hidden lg:inline' : 'hidden'}>
              pv
            </span>
          </DocumentNavLink>
          <button
            type="button"
            aria-label={sidebarCollapsed ? 'Admin 메뉴 펼치기' : 'Admin 메뉴 접기'}
            title={sidebarCollapsed ? 'Admin 메뉴 펼치기' : 'Admin 메뉴 접기'}
            aria-pressed={sidebarCollapsed}
            data-testid="admin-sidebar-toggle"
            className="hidden size-9 shrink-0 items-center justify-center rounded-control text-muted hover:bg-admin-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary lg:flex"
            onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
          >
            {sidebarCollapsed ? (
              <ChevronsRight className="size-4" aria-hidden="true" />
            ) : (
              <ChevronsLeft className="size-4" aria-hidden="true" />
            )}
          </button>
        </div>
        <div
          className="pinvi-common-menu min-h-0 max-w-full overflow-x-auto px-2 py-2 lg:flex-1 lg:overflow-x-hidden lg:overflow-y-auto"
          data-collapsed={sidebarCollapsed}
        >
          <AppMenu
            groups={COMMON_MENU_GROUPS}
            pathname={pathname}
            linkComponent={CommonDocumentLink}
            label="관리자 주요 메뉴"
            testId="admin-common-menu"
          />
        </div>
        <footer className="flex shrink-0 flex-wrap items-center gap-2 border-t border-admin-line p-2 lg:flex-col lg:items-stretch">
          <div
            className="flex min-w-0 items-center gap-2 px-2 py-1 text-xs text-muted"
            data-testid="admin-me"
            title={me.email}
            aria-label={`로그인 사용자 ${me.email}`}
          >
            <UserRound className="size-4 shrink-0" aria-hidden="true" />
            <span className={sidebarCollapsed ? 'truncate lg:sr-only' : 'truncate'}>
              {me.roles.filter((r) => r !== 'user').join(', ') || 'user'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            disabled={loggingOut}
            aria-label="로그아웃"
            title="로그아웃"
            className="flex min-h-11 items-center gap-2 rounded-control lg:min-h-9 px-3 text-xs text-muted hover:bg-admin-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-wait"
          >
            <LogOut className="size-4 shrink-0" aria-hidden="true" />
            <span className={sidebarCollapsed ? 'lg:sr-only' : ''}>
              {loggingOut ? '로그아웃 중…' : '로그아웃'}
            </span>
          </button>
          {logoutError ? (
            <p role="alert" className="text-xs text-admin-danger">
              {logoutError}
            </p>
          ) : null}
        </footer>
      </aside>
      {/* `tabIndex={-1}`이라야 skip link가 실제로 포커스를 옮긴다(그냥 앵커면 스크롤만 되고
          다음 Tab이 nav로 되돌아간다). 링 자체는 이 컨테이너에 필요 없어 끈다. */}
      <main
        className="min-w-0 flex-1 overflow-x-clip px-4 py-6 focus-visible:outline-0 sm:px-6 lg:px-8 lg:py-8"
        id={ADMIN_MAIN_CONTENT_ID}
        tabIndex={-1}
      >
        {children}
      </main>
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
