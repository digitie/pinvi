'use client';

import { ADMIN_MAIN_CONTENT_ID } from '@/components/admin/admin-shell-parts';
import { AdminQueryProvider } from '@/components/admin/AdminQueryProvider';
import {
  AdminShell,
  AppMenu,
  type AdminShellSlotState,
  type AppMenuGroup,
  type AppMenuLinkProps,
} from '@kor-travel/ui';
import { ApiClient, ApiError, authApi, queryKeys } from '@pinvi/api-client';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Archive,
  Ban,
  BarChart3,
  Bug,
  ClipboardCheck,
  Gavel,
  GitCompare,
  HardDrive,
  KeyRound,
  LayoutDashboard,
  Lightbulb,
  LogOut,
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
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { redirect, usePathname, useRouter } from 'next/navigation';
import { useState, type ReactNode } from 'react';
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
/** 접힘 상태 저장 키. 공통 셸이 기존 "1"/"0" 저장값을 그대로 읽고 같은 형식으로 쓴다. */
const SIDEBAR_COLLAPSED_STORAGE_KEY = 'pinvi.admin.sidebar.collapsed';
const ADMIN_AREA_FALLBACK = 'Pinvi 관리';
const ADMIN_SHELL_LABELS = {
  openMenu: 'Admin 메뉴 열기',
  closeMenu: 'Admin 메뉴 닫기',
  menu: 'Admin 메뉴',
  collapseRail: 'Admin 메뉴 접기',
  expandRail: 'Admin 메뉴 펼치기',
};

function adminSection(pathname: string) {
  return pathname.split('/').slice(0, 3).join('/');
}

/**
 * 상단 바 기본 제목("영역 - 페이지")을 nav 정본에서 고른다. 영역은 메뉴 그룹, 페이지는 메뉴 라벨이다.
 * 하위 경로(상세 등)는 가장 긴 href 접두사를, 그것도 없으면 같은 `/admin/<구역>`의 항목을 쓴다.
 * 페이지가 `AdminPage`로 더 구체적인 제목을 주면 그 값이 덮어쓴다.
 */
function adminNavTitle(pathname: string): { area: string; title?: string } {
  let best: { area: string; title: string; score: number } | null = null;
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      const exact = pathname === item.href;
      const nested = item.href !== '/admin' && pathname.startsWith(`${item.href}/`);
      const sameSection =
        item.href !== '/admin' && adminSection(item.href) === adminSection(pathname);
      const score = exact || nested ? item.href.length + 1000 : sameSection ? item.href.length : -1;
      if (score >= 0 && (!best || score > best.score))
        best = { area: group.title, title: item.label, score };
    }
  }
  return best ? { area: best.area, title: best.title } : { area: ADMIN_AREA_FALLBACK };
}

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
function AdminGuard(...args: Parameters<typeof useAdminGuardModel>) {
  const viewModel = useAdminGuardModel(...args);
  if (viewModel.renderBranch === 'render0') return <AdminGuardView0 viewModel={viewModel} />;
  if (viewModel.renderBranch === 'render1') return <AdminGuardView1 />;
  if (viewModel.renderBranch === 'render2') return <AdminGuardView2 viewModel={viewModel} />;
  if (viewModel.renderBranch === 'render3') return <AdminGuardView3 />;
  if (viewModel.renderBranch === 'render4') return <AdminGuardView4 viewModel={viewModel} />;
  return null;
}

function adminLoginDestination(
  isLoginPage: boolean,
  query: { isError: boolean; isSuccess: boolean; error: unknown },
  hasMe: boolean,
  hasAdmin: boolean,
) {
  if (isLoginPage) return null;
  if (
    query.isError &&
    query.error instanceof ApiError &&
    (query.error.status === 401 || query.error.status === 404)
  )
    return '/admin/login';
  if (query.isSuccess && hasMe && !hasAdmin) return '/admin/login?reason=forbidden';
  return null;
}

function useAdminGuardModel({ children }: { children: ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
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

  const destination = adminLoginDestination(isLoginPage, meQuery, Boolean(me), hasAdmin);
  if (destination) redirect(destination);

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
    return { renderBranch: 'render0' as const, children };
  }
  if (meQuery.isPending) {
    return { renderBranch: 'render1' as const };
  }
  if (meQuery.isError) {
    return { renderBranch: 'render2' as const, meQuery };
  }
  if (!me || !hasAdmin) return { renderBranch: 'render3' as const };

  return {
    renderBranch: 'render4' as const,
    children,
    loggingOut,
    logout,
    logoutError,
    me,
    pathname,
  };
}

type AdminGuardView0Model = Extract<
  ReturnType<typeof useAdminGuardModel>,
  { renderBranch: 'render0' }
>;
function AdminGuardView0({ viewModel }: { viewModel: AdminGuardView0Model }) {
  const { children } = viewModel;
  return <div className="min-h-dvh bg-surface-soft">{children}</div>;
}
function AdminGuardView1() {
  return (
    <div className="flex min-h-dvh items-center justify-center text-sm text-muted">
      권한 확인 중…
    </div>
  );
}

type AdminGuardView2Model = Extract<
  ReturnType<typeof useAdminGuardModel>,
  { renderBranch: 'render2' }
>;
function AdminGuardView2({ viewModel }: { viewModel: AdminGuardView2Model }) {
  const { meQuery } = viewModel;
  return (
    <div className="p-8" role="alert">
      권한을 확인하지 못했습니다.
      <button type="button" onClick={() => void meQuery.refetch()} className="ml-3 underline">
        다시 확인
      </button>
    </div>
  );
}
function AdminGuardView3() {
  return null;
}

type AdminGuardView4Model = Extract<
  ReturnType<typeof useAdminGuardModel>,
  { renderBranch: 'render4' }
>;
function AdminGuardView4({ viewModel }: { viewModel: AdminGuardView4Model }) {
  const { children, loggingOut, logout, logoutError, me, pathname } = viewModel;
  const navTitle = adminNavTitle(pathname);
  // 공통 AdminShell(@kor-travel/ui 0.2.3): lg 이상은 좌측 rail(접힘 4rem), 미만은 상단 바 메뉴
  // 버튼으로 여는 좌측 drawer다. 맨 위 한 줄은 "영역 - 페이지" 제목과 작은 설명만 둔다 — 페이지는
  // `AdminPage`가 `AdminPageTitle`로 제목·설명을 덮어쓴다. 셸 안 AppMenu에는 orientation을 주지 않는다
  // (rail·drawer가 배치를 알린다). drawer는 Portal이라 `[data-pv-surface='admin']` 밖으로 나가므로
  // globals.css가 `[data-slot='admin-shell-drawer']`에도 같은 admin 토큰을 건다.
  return (
    <AdminShell
      testId="admin-shell"
      area={navTitle.area}
      title={navTitle.title}
      navigationKey={pathname}
      collapsedStorageKey={SIDEBAR_COLLAPSED_STORAGE_KEY}
      mainId={ADMIN_MAIN_CONTENT_ID}
      mainClassName="overflow-x-clip px-4 py-6 sm:px-6 lg:px-8"
      labels={ADMIN_SHELL_LABELS}
      brand={AdminBrand}
      railFooter={(state) => (
        <AdminRailFooter
          state={state}
          email={me.email}
          roles={me.roles}
          loggingOut={loggingOut}
          logout={logout}
          logoutError={logoutError}
        />
      )}
      menu={
        <AppMenu
          groups={COMMON_MENU_GROUPS}
          pathname={pathname}
          linkComponent={CommonDocumentLink}
          label="관리자 주요 메뉴"
          testId="admin-common-menu"
        />
      }
    >
      {children}
    </AdminShell>
  );
}

function AdminBrand({ collapsed }: AdminShellSlotState) {
  return (
    <DocumentNavLink
      href="/admin"
      aria-label="Pinvi Admin"
      title={collapsed ? 'Pinvi Admin' : undefined}
      className="flex min-w-0 items-baseline gap-2 rounded-control text-sm font-semibold tracking-tight text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kt-focus"
    >
      {collapsed ? (
        <span aria-hidden="true">pv</span>
      ) : (
        <>
          <span>Pinvi</span>
          <span className="text-xs text-muted">admin</span>
        </>
      )}
    </DocumentNavLink>
  );
}

function AdminRailFooter({
  state,
  email,
  roles,
  loggingOut,
  logout,
  logoutError,
}: {
  state: AdminShellSlotState;
  email: string;
  roles: string[];
  loggingOut: boolean;
  logout: () => Promise<void>;
  logoutError: string | null;
}) {
  const { collapsed } = state;
  return (
    <div className="flex flex-col gap-1">
      <div
        className={`flex min-w-0 items-center gap-2 py-1 text-xs text-muted ${collapsed ? 'justify-center' : 'px-2'}`}
        data-testid="admin-me"
        title={email}
        aria-label={`로그인 사용자 ${email}`}
      >
        <UserRound className="size-4 shrink-0" aria-hidden="true" />
        <span className={collapsed ? 'sr-only' : 'truncate'}>
          {roles.filter((r) => r !== 'user').join(', ') || 'user'}
        </span>
      </div>
      <button
        type="button"
        onClick={() => void logout()}
        disabled={loggingOut}
        aria-label="로그아웃"
        title="로그아웃"
        className={`flex min-h-11 items-center gap-2 rounded-control text-xs text-muted hover:bg-admin-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-kt-focus disabled:cursor-wait lg:min-h-9 ${collapsed ? 'justify-center px-0' : 'px-3'}`}
      >
        <LogOut className="size-4 shrink-0" aria-hidden="true" />
        <span className={collapsed ? 'sr-only' : ''}>{loggingOut ? '로그아웃 중…' : '로그아웃'}</span>
      </button>
      {logoutError ? (
        <p role="alert" className="text-xs text-admin-danger">
          {logoutError}
        </p>
      ) : null}
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
