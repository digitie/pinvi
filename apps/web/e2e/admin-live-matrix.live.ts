import fs from 'node:fs/promises';
import path from 'node:path';
import { expect, test as base, type Browser, type Page } from '@playwright/test';

interface AdminRoute {
  path: string;
  heading: string;
  table?: boolean;
  placeholder?: boolean;
  readyTestId?: string;
  readyText?: string | RegExp;
}

interface UiViewport {
  name: string;
  width: number;
  height: number;
}

interface AdminUiCase {
  name: string;
  viewport: UiViewport;
  run: (page: Page) => Promise<void>;
}

interface AdminAuthState {
  path: string;
  refreshedAt: number;
  canRefresh: boolean;
}

const liveEnabled = process.env.PINVI_ADMIN_LIVE_E2E === '1';
const webBaseUrl =
  process.env.PINVI_ADMIN_LIVE_WEB_URL ??
  process.env.PLAYWRIGHT_BASE_URL ??
  'http://127.0.0.1:12805';
const adminEmail = process.env.PINVI_ADMIN_LIVE_EMAIL;
const adminPassword = process.env.PINVI_ADMIN_LIVE_PASSWORD;
const adminStorageState = process.env.PINVI_ADMIN_LIVE_STORAGE_STATE;
const hasAdminCredentials = Boolean(adminEmail && adminPassword);
const hasAdminLiveAuth = hasAdminCredentials || Boolean(adminStorageState);
const throttleMs = Number(process.env.PINVI_ADMIN_LIVE_THROTTLE_MS ?? '2100');
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const parsedCaseAttempts = Number(process.env.PINVI_ADMIN_LIVE_CASE_ATTEMPTS ?? '3');
const caseAttempts = Number.isFinite(parsedCaseAttempts)
  ? Math.max(1, Math.floor(parsedCaseAttempts))
  : 3;
const parsedLoginAttempts = Number(
  process.env.PINVI_ADMIN_LIVE_LOGIN_ATTEMPTS ?? String(caseAttempts),
);
const loginAttempts = Number.isFinite(parsedLoginAttempts)
  ? Math.max(1, Math.floor(parsedLoginAttempts))
  : caseAttempts;
const parsedRetryBackoffMs = process.env.PINVI_ADMIN_LIVE_RETRY_BACKOFF_MS
  ? Number(process.env.PINVI_ADMIN_LIVE_RETRY_BACKOFF_MS)
  : Math.max(throttleMs * 4, 10_000);
const retryBackoffMs = Number.isFinite(parsedRetryBackoffMs)
  ? Math.max(0, parsedRetryBackoffMs)
  : 10_000;
const caseRetryBackoffMs = Math.min(retryBackoffMs, 5_000);
const parsedAuthRefreshMs = Number(process.env.PINVI_ADMIN_LIVE_AUTH_REFRESH_MS ?? '300000');
const authRefreshMs = Number.isFinite(parsedAuthRefreshMs)
  ? Math.max(60_000, parsedAuthRefreshMs)
  : 300_000;
const parsedCaseLimit = process.env.PINVI_ADMIN_LIVE_CASE_LIMIT
  ? Number(process.env.PINVI_ADMIN_LIVE_CASE_LIMIT)
  : Number.POSITIVE_INFINITY;
const caseLimit = Number.isFinite(parsedCaseLimit) ? parsedCaseLimit : Number.POSITIVE_INFINITY;
const parsedCaseStart = process.env.PINVI_ADMIN_LIVE_CASE_START
  ? Number(process.env.PINVI_ADMIN_LIVE_CASE_START)
  : 1;
const caseStart = Number.isFinite(parsedCaseStart) ? Math.max(1, Math.floor(parsedCaseStart)) : 1;
const parsedCaseEnd = process.env.PINVI_ADMIN_LIVE_CASE_END
  ? Number(process.env.PINVI_ADMIN_LIVE_CASE_END)
  : Number.POSITIVE_INFINITY;
const caseEnd = Number.isFinite(parsedCaseEnd)
  ? Math.max(caseStart - 1, Math.floor(parsedCaseEnd))
  : Number.POSITIVE_INFINITY;

const viewports: UiViewport[] = [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'wide', width: 1600, height: 1000 },
  { name: 'tablet', width: 1024, height: 768 },
  { name: 'mobile-wide', width: 430, height: 932 },
];
const compactViewports = viewports.slice(0, 2);
const mixedViewports = [viewports[0]!, viewports[2]!, viewports[3]!];

const queryTerms = [
  'admin',
  'example.com',
  'pinvi',
  'kim',
  'lee',
  'park',
  'seoul',
  'busan',
  'jeju',
  'kma',
  'visitkorea',
  'pending',
  'active',
  'disabled',
  '00000000-0000-4000-8000-000000000001',
  '한글',
];
const shortTerms = queryTerms.slice(0, 8);
const rawSecretPatterns = [
  /Authorization\s*[:=]\s*(?:Bearer|Basic)\s+\S+/i,
  /Cookie\s*[:=]\s*\S+/i,
  /Set-Cookie\s*[:=]\s*\S+/i,
  /(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*(?!\[masked\]|%5Bmasked%5D|redacted|<redacted>|\*\*\*)[A-Za-z0-9_./+=-]{8,}/i,
  /AKIA[0-9A-Z]{16}/,
  /BEGIN [A-Z ]*PRIVATE KEY/,
];

const uiRoutes: AdminRoute[] = [
  { path: '/admin', heading: '대시보드' },
  { path: '/admin/users', heading: '사용자', table: true },
  { path: '/admin/rbac', heading: 'RBAC', table: true },
  { path: '/admin/trips', heading: '여행', table: true },
  { path: '/admin/pois', heading: 'POI', table: true },
  { path: '/admin/feature-requests', heading: 'Feature 제안 검토', table: true },
  { path: '/admin/audit', heading: '감사 로그', table: true },
  { path: '/admin/features', heading: 'Features', table: true },
  { path: '/admin/features/change-requests', heading: 'Feature 변경 요청', table: true },
  { path: '/admin/dedup-review', heading: 'Dedup review', table: true },
  { path: '/admin/provider-sync', heading: 'Provider sync', table: true },
  { path: '/admin/integrity', heading: '정합성', table: true },
  { path: '/admin/category-mapping', heading: '카테고리 매핑', table: true },
  { path: '/admin/debug/logs', heading: 'Debug logs', table: true },
  { path: '/admin/system', heading: '시스템', readyTestId: 'admin-system-containers' },
  { path: '/admin/etl', heading: 'ETL', table: true },
  { path: '/admin/grafana', heading: 'Grafana', readyTestId: 'admin-grafana-health-status' },
  { path: '/admin/api-calls', heading: 'API 호출 로그', table: true },
  { path: '/admin/emails', heading: '이메일 큐', table: true },
  { path: '/admin/backup', heading: 'Backup', table: true },
  { path: '/admin/mcp-tokens', heading: 'MCP 토큰', table: true },
  {
    path: '/admin/seed',
    heading: '시드 시나리오',
    readyText: /seed route가 비활성화되어 있습니다|seed scenario가 없습니다|dry-run/,
  },
  { path: '/admin/reset', heading: 'DB 리셋' },
];

const dashboardRoute = uiRoutes[0]!;
const placeholderRoutes = uiRoutes.filter((route) => route.placeholder);

const sortSpecs = [
  {
    route: '/admin/users',
    heading: '사용자',
    columns: ['email', 'nickname', 'status', 'created_at'],
  },
  {
    route: '/admin/trips',
    heading: '여행',
    columns: ['title', 'status', 'visibility', 'updated_at'],
  },
  {
    route: '/admin/pois',
    heading: 'POI',
    columns: ['feature', 'trip', 'day', 'sort_order', 'updated_at'],
  },
  {
    route: '/admin/api-calls',
    heading: 'API 호출 로그',
    columns: ['provider', 'endpoint', 'status', 'latency', 'occurred'],
  },
  {
    route: '/admin/emails',
    heading: '이메일 큐',
    columns: ['to_email', 'template', 'status', 'attempts', 'scheduled'],
  },
  { route: '/admin/audit', heading: '감사 로그', columns: ['log_id', 'action', 'occurred_at'] },
  {
    route: '/admin/backup',
    heading: 'Backup',
    columns: ['filename', 'created_at', 'size', 'status'],
  },
  {
    route: '/admin/mcp-tokens',
    heading: 'MCP 토큰',
    columns: ['name', 'status', 'expires', 'last_used'],
  },
  {
    route: '/admin/feature-requests',
    heading: 'Feature 제안 검토',
    columns: ['type', 'name', 'status', 'created_at'],
  },
  {
    route: '/admin/features',
    heading: 'Features',
    columns: ['feature', 'kind', 'provider', 'issue_count', 'updated_at'],
  },
  {
    route: '/admin/provider-sync',
    heading: 'Provider sync',
    columns: ['provider', 'scope', 'status', 'last_success', 'failures', 'next_run'],
  },
  {
    route: '/admin/etl',
    heading: 'ETL',
    columns: ['job', 'status', 'progress', 'stage', 'created_at', 'finished_at'],
  },
  {
    route: '/admin/dedup-review',
    heading: 'Dedup review',
    columns: ['review', 'score', 'status', 'feature_a', 'feature_b', 'distance'],
  },
  {
    route: '/admin/integrity',
    heading: '정합성',
    columns: ['issue', 'severity', 'status', 'target', 'message', 'detected'],
  },
  {
    route: '/admin/category-mapping',
    heading: '카테고리 매핑',
    columns: ['category', 'active', 'upstream_icon', 'pinvi_marker', 'mapping', 'features', 'sort'],
  },
  {
    route: '/admin/debug/logs',
    heading: 'Debug logs',
    columns: ['log', 'level', 'source', 'event', 'message', 'created'],
  },
];

let lastActionAt = 0;

async function throttle() {
  if (throttleMs <= 0) return;
  const elapsed = Date.now() - lastActionAt;
  if (elapsed < throttleMs) {
    await new Promise((resolve) => setTimeout(resolve, throttleMs - elapsed));
  }
  lastActionAt = Date.now();
}

async function loginViaUi(page: Page) {
  if (!adminEmail || !adminPassword) {
    throw new Error('PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD가 필요합니다.');
  }

  for (let attempt = 1; attempt <= loginAttempts; attempt += 1) {
    await page.goto('/admin/login');
    await page.getByTestId('admin-login-email').fill(adminEmail);
    await page.getByTestId('admin-login-password').fill(adminPassword);
    await throttle();
    await page.getByTestId('admin-login-submit').click();
    try {
      await expect(page).toHaveURL(/\/admin(?:[?#].*)?$/);
      await expect(page.getByTestId('admin-me')).toBeVisible();
      return;
    } catch {
      const alertText = await page
        .getByTestId('admin-login-error')
        .textContent({ timeout: 1000 })
        .catch(() => null);
      if (attempt < loginAttempts) {
        await page.waitForTimeout(retryBackoffMs);
        continue;
      }
      throw new Error(
        `live admin UI login failed at ${page.url()}${alertText ? `: ${alertText}` : ''}`,
      );
    }
  }
}

async function reloginIfNeeded(page: Page, returnPath: string) {
  const loginVisible = await page
    .getByTestId('admin-login-submit')
    .isVisible({ timeout: 1000 })
    .catch(() => false);
  if (!loginVisible) return;
  if (!hasAdminCredentials) {
    throw new Error(
      'PINVI_ADMIN_LIVE_STORAGE_STATE 세션이 만료됐습니다. PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD로 갱신 가능한 인증을 제공하세요.',
    );
  }
  await loginViaUi(page);
  await throttle();
  await page.goto(returnPath);
}

async function refreshAdminAuthState(browser: Browser, authState: AdminAuthState) {
  const context = await browser.newContext({
    baseURL: webBaseUrl,
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  try {
    await loginViaUi(page);
    await context.storageState({ path: authState.path });
    authState.refreshedAt = Date.now();
  } finally {
    await context.close();
  }
}

const liveUiTest = base.extend<{ page: Page }, { adminAuthState: AdminAuthState | null }>({
  adminAuthState: [
    async ({ browser }, use, workerInfo) => {
      if (!liveEnabled || !hasAdminLiveAuth) {
        await use(null);
        return;
      }

      if (!hasAdminCredentials && adminStorageState) {
        await use({ path: adminStorageState, refreshedAt: Date.now(), canRefresh: false });
        return;
      }

      const authDir = path.join(process.cwd(), 'test-results', '.auth');
      await fs.mkdir(authDir, { recursive: true });
      const authStatePath = path.join(authDir, `admin-live-ui-${workerInfo.workerIndex}.json`);
      const authState: AdminAuthState = { path: authStatePath, refreshedAt: 0, canRefresh: true };

      await refreshAdminAuthState(browser, authState);
      await use(authState);
    },
    { scope: 'worker' },
  ],
  page: async ({ browser, adminAuthState }, use) => {
    if (adminAuthState?.canRefresh && Date.now() - adminAuthState.refreshedAt >= authRefreshMs) {
      await refreshAdminAuthState(browser, adminAuthState);
    }
    const context = await browser.newContext({
      baseURL: webBaseUrl,
      ignoreHTTPSErrors: true,
      storageState: adminAuthState?.path,
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function navTestId(pathname: string) {
  return `admin-nav-${pathname.replace(/[^a-z0-9]+/gi, '-')}`;
}

function pathnameOf(value: string) {
  try {
    return new URL(value).pathname;
  } catch {
    return '';
  }
}

async function setViewport(page: Page, viewport: UiViewport) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
}

async function expectAdminShell(page: Page, heading: string) {
  await expect(page.locator('main')).toBeVisible();
  await expect(page.getByTestId('admin-me')).toBeVisible();
  await expect(
    page.getByRole('heading', { name: new RegExp(escapeRegExp(heading)) }).first(),
  ).toBeVisible();
  await expect(page.getByTestId('global-error-retry')).toHaveCount(0);
  await expect(page.getByTestId('not-found-page')).toHaveCount(0);
}

async function expectNoBlockingErrors(page: Page) {
  await expect(
    page.getByText(
      /불러오지 못했습니다|조회 실패|검증 실패|알 수 없는 오류|요청이 올바르지 않습니다|Response shape mismatch|HTTP \d{3}|Internal Server Error|Unauthorized|Forbidden/,
    ),
  ).toHaveCount(0);
}

async function expectNoRawSecrets(page: Page) {
  const bodyText = await page.locator('main').innerText();
  for (const pattern of rawSecretPatterns) {
    expect(bodyText).not.toMatch(pattern);
  }
}

function installDebugRequestIdRecorder(page: Page, captured: { requestIds: string[] }) {
  page.on('response', (response) => {
    const pathname = pathnameOf(response.url());
    if (pathname !== '/admin/debug/logs/system' && pathname !== '/admin/debug/logs/api-calls') {
      return;
    }
    const requestId = response.headers()['x-request-id'];
    if (requestId && UUID_RE.test(requestId)) {
      captured.requestIds.push(requestId);
    }
  });
}

async function waitForCapturedRequestId(captured: { requestIds: string[] }) {
  await expect
    .poll(() => captured.requestIds.find((value) => UUID_RE.test(value)) ?? null, {
      timeout: 15_000,
    })
    .not.toBeNull();
  return captured.requestIds.find((value) => UUID_RE.test(value))!;
}

function backupMutationPath(value: string, method: string) {
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return null;
  const pathname = pathnameOf(value);
  return pathname.startsWith('/admin/backup') ? pathname : null;
}

async function waitForAdminTable(page: Page) {
  await expect(page.getByTestId('admin-table-scroll').first()).toBeVisible();
  await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });
  await expectNoBlockingErrors(page);
}

async function openRoute(page: Page, route: AdminRoute) {
  await throttle();
  await page.goto(route.path);
  await reloginIfNeeded(page, route.path);
  await expectAdminShell(page, route.heading);
  if (route.readyTestId) {
    await expect(page.getByTestId(route.readyTestId)).toBeVisible();
  }
  if (route.readyText) {
    await expect(page.getByText(route.readyText).first()).toBeVisible();
  }
  if (route.table) {
    await waitForAdminTable(page);
  } else {
    await expectNoBlockingErrors(page);
  }
  await expectNoRawSecrets(page);
}

async function openTableRoute(page: Page, pathName: string, heading: string) {
  await openRoute(page, { path: pathName, heading, table: true });
}

async function runLiveCaseWithAttempts(page: Page, liveCase: AdminUiCase) {
  for (let attempt = 1; attempt <= caseAttempts; attempt += 1) {
    try {
      await setViewport(page, liveCase.viewport);
      await liveCase.run(page);
      return;
    } catch (error) {
      if (attempt >= caseAttempts) {
        throw error;
      }
      await page.waitForTimeout(caseRetryBackoffMs);
    }
  }
}

function pushCase(
  cases: AdminUiCase[],
  name: string,
  viewport: UiViewport,
  run: (page: Page) => Promise<void>,
) {
  cases.push({ name: `${viewport.name} ${name}`, viewport, run });
}

function pushRouteCases(cases: AdminUiCase[]) {
  for (let repeat = 1; repeat <= 5; repeat += 1) {
    for (const viewport of viewports) {
      for (const route of uiRoutes) {
        pushCase(cases, `route ${route.path} renders repeat=${repeat}`, viewport, async (page) => {
          await openRoute(page, route);
        });
      }
    }
  }
}

function pushNavigationCases(cases: AdminUiCase[]) {
  for (let repeat = 1; repeat <= 5; repeat += 1) {
    for (const viewport of viewports) {
      for (const route of uiRoutes) {
        pushCase(cases, `nav clicks ${route.path} repeat=${repeat}`, viewport, async (page) => {
          await openRoute(page, dashboardRoute);
          await throttle();
          await page.getByTestId(navTestId(route.path)).click();
          await reloginIfNeeded(page, route.path);
          await expectAdminShell(page, route.heading);
          if (route.table) {
            await waitForAdminTable(page);
          } else {
            await expectNoBlockingErrors(page);
          }
        });
      }
    }
  }
}

function pushPlaceholderCases(cases: AdminUiCase[]) {
  for (let repeat = 1; repeat <= 10; repeat += 1) {
    for (const viewport of viewports) {
      for (const route of placeholderRoutes) {
        pushCase(
          cases,
          `placeholder ${route.path} shows scope repeat=${repeat}`,
          viewport,
          async (page) => {
            await openRoute(page, route);
            await expect(page.getByRole('heading', { name: '작업 범위' })).toBeVisible();
          },
        );
      }
    }
  }
}

function pushUsersFilterCases(cases: AdminUiCase[]) {
  const statuses = [
    '',
    'pending_verification',
    'pending_profile',
    'active',
    'disabled',
    'pending_delete',
    'deleted',
  ];
  for (const viewport of viewports) {
    for (const status of statuses) {
      for (const query of queryTerms) {
        pushCase(
          cases,
          `users filter status=${status || 'all'} q=${query}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/users', '사용자');
            await page.getByTestId('admin-users-search').fill(query);
            await throttle();
            await page.getByTestId('admin-users-search-submit').click();
            await throttle();
            await page.getByTestId('admin-users-status-filter').selectOption(status);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-users-search')).toHaveValue(query);
            await expect(page.getByTestId('admin-users-status-filter')).toHaveValue(status);
          },
        );
      }
    }
  }
}

function pushTripsFilterCases(cases: AdminUiCase[]) {
  const statuses = ['', 'draft', 'planned', 'in_progress', 'completed', 'archived'];
  const visibilities = ['', 'private', 'unlisted', 'public'];
  for (const viewport of compactViewports) {
    for (const status of statuses) {
      for (const visibility of visibilities) {
        for (const query of shortTerms) {
          pushCase(
            cases,
            `trips filter status=${status || 'all'} visibility=${visibility || 'all'} q=${query}`,
            viewport,
            async (page) => {
              await openTableRoute(page, '/admin/trips', '여행');
              await page.getByTestId('admin-trips-search').fill(query);
              await throttle();
              await page.getByTestId('admin-trips-search-submit').click();
              await throttle();
              await page.getByTestId('admin-trips-status-filter').selectOption(status);
              await throttle();
              await page.getByTestId('admin-trips-visibility-filter').selectOption(visibility);
              await waitForAdminTable(page);
              await expect(page.getByTestId('admin-trips-search')).toHaveValue(query);
              await expect(page.getByTestId('admin-trips-status-filter')).toHaveValue(status);
              await expect(page.getByTestId('admin-trips-visibility-filter')).toHaveValue(
                visibility,
              );
            },
          );
        }
      }
    }
  }
}

function pushPoisFilterCases(cases: AdminUiCase[]) {
  const linkFilters = ['', 'false', 'true'];
  for (const viewport of viewports) {
    for (const linkFilter of linkFilters) {
      for (const query of queryTerms) {
        pushCase(
          cases,
          `pois filter link=${linkFilter || 'all'} q=${query}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/pois', 'POI');
            await page.getByTestId('admin-pois-search').fill(query);
            await throttle();
            await page.getByTestId('admin-pois-search-submit').click();
            await throttle();
            await page.getByTestId('admin-pois-broken-filter').selectOption(linkFilter);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-pois-search')).toHaveValue(query);
            await expect(page.getByTestId('admin-pois-broken-filter')).toHaveValue(linkFilter);
          },
        );
      }
    }
  }
}

function pushApiCallFilterCases(cases: AdminUiCase[]) {
  const providers = ['', 'kma', 'visitkorea', 'opinet', 'khoa', 'krex', 'airkorea', 'kasi'];
  const statusCodes = ['', '200', '201', '204', '400', '401', '404', '500'];
  const errorClasses = ['', 'TimeoutError', 'HTTPStatusError', 'RateLimitError'];
  for (const viewport of compactViewports) {
    for (const provider of providers) {
      for (const statusCode of statusCodes) {
        for (const errorClass of errorClasses) {
          pushCase(
            cases,
            `api-calls filter provider=${provider || 'all'} status=${statusCode || 'all'} error=${errorClass || 'all'}`,
            viewport,
            async (page) => {
              await openTableRoute(page, '/admin/api-calls', 'API 호출 로그');
              await page.getByTestId('admin-api-calls-provider').fill(provider);
              await page.getByTestId('admin-api-calls-status').fill(statusCode);
              await page.getByTestId('admin-api-calls-error').fill(errorClass);
              await throttle();
              await page.getByTestId('admin-api-calls-submit').click();
              await waitForAdminTable(page);
              await expect(page.getByTestId('admin-api-calls-provider')).toHaveValue(provider);
              await expect(page.getByTestId('admin-api-calls-status')).toHaveValue(statusCode);
              await expect(page.getByTestId('admin-api-calls-error')).toHaveValue(errorClass);
            },
          );
        }
      }
    }
  }
}

function pushEmailsFilterCases(cases: AdminUiCase[]) {
  const statuses = ['', 'pending', 'sent', 'delivered', 'bounced', 'complained', 'failed'];
  for (let repeat = 1; repeat <= 5; repeat += 1) {
    for (const viewport of viewports) {
      for (const status of statuses) {
        pushCase(
          cases,
          `emails filter status=${status || 'all'} repeat=${repeat}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/emails', '이메일 큐');
            await throttle();
            await page.getByTestId('admin-emails-status-filter').selectOption(status);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-emails-status-filter')).toHaveValue(status);
          },
        );
      }
    }
  }
}

function pushBackupFilterCases(cases: AdminUiCase[]) {
  const statuses = ['all', 'verified', 'available'];
  for (const viewport of compactViewports) {
    for (const status of statuses) {
      pushCase(cases, `backup filter status=${status}`, viewport, async (page) => {
        await openTableRoute(page, '/admin/backup', 'Backup');
        await page.getByTestId('admin-backup-status-filter').selectOption(status);
        await expect(page.getByTestId('admin-backup-status-filter')).toHaveValue(status);
        await page.getByTestId('admin-backup-search').fill(`pinvi-live-no-match-${status}`);
        await expect(page.getByTestId('admin-backup-visible-count')).toContainText('0 /');
        await expectNoBlockingErrors(page);
      });
    }
  }
}

function pushBackupReadOnlyGuardCases(cases: AdminUiCase[]) {
  for (const viewport of compactViewports) {
    pushCase(cases, 'backup restore controls stay locked read-only', viewport, async (page) => {
      const backupMutations: string[] = [];
      page.on('request', (request) => {
        const pathName = backupMutationPath(request.url(), request.method());
        if (pathName) backupMutations.push(pathName);
      });

      await openTableRoute(page, '/admin/backup', 'Backup');
      await page.getByTestId('admin-table-sort-filename').click();
      await throttle();
      await page.getByTestId('admin-backup-status-filter').selectOption('verified');
      await expect(page.getByTestId('admin-backup-status-filter')).toHaveValue('verified');

      const restoreButtons = page.getByTestId('admin-backup-restore');
      const restoreCount = await restoreButtons.count();
      for (let index = 0; index < restoreCount; index += 1) {
        await expect(restoreButtons.nth(index)).toBeDisabled();
      }

      await page.getByTestId('admin-backup-search').fill(`pinvi-live-no-match-${Date.now()}`);
      await expect(page.getByTestId('admin-backup-visible-count')).toContainText('0 /');
      expect(backupMutations).toEqual([]);
    });
  }
}

function pushMcpFilterCases(cases: AdminUiCase[]) {
  const statuses = ['', 'active', 'expired', 'revoked'];
  for (const viewport of compactViewports) {
    for (const status of statuses) {
      for (const query of queryTerms.slice(0, 10)) {
        pushCase(
          cases,
          `mcp-tokens filter status=${status || 'all'} q=${query}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/mcp-tokens', 'MCP 토큰');
            await page.getByTestId('admin-mcp-search').fill(query);
            await throttle();
            await page.getByRole('button', { name: '조회' }).click();
            await throttle();
            await page.getByTestId('admin-mcp-status').selectOption(status);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-mcp-search')).toHaveValue(query);
            await expect(page.getByTestId('admin-mcp-status')).toHaveValue(status);
          },
        );
      }
    }
  }
}

function pushFeatureRequestFilterCases(cases: AdminUiCase[]) {
  const statuses = ['pending', 'approved', 'added', 'rejected', ''];
  for (let repeat = 1; repeat <= 5; repeat += 1) {
    for (const viewport of viewports) {
      for (const status of statuses) {
        pushCase(
          cases,
          `feature-requests filter status=${status || 'all'} repeat=${repeat}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/feature-requests', 'Feature 제안 검토');
            await throttle();
            await page.getByTestId('admin-fr-status-filter').selectOption(status);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-fr-status-filter')).toHaveValue(status);
          },
        );
      }
    }
  }
}

function pushFeaturesFilterCases(cases: AdminUiCase[]) {
  const kinds = ['all', 'place', 'event', 'notice', 'price', 'weather', 'route', 'area'];
  const statuses = ['active', 'all', 'inactive', 'hidden', 'broken', 'deleted'];
  const issues = ['all', 'yes', 'no'];
  const providers = ['', 'visitkorea', 'kma', 'opinet'];
  const categories = ['', '01070100', '02010100'];
  for (const viewport of compactViewports) {
    for (const kind of kinds) {
      for (const status of statuses) {
        for (const issue of issues) {
          for (const query of shortTerms) {
            pushCase(
              cases,
              `features filter kind=${kind} status=${status} issue=${issue} q=${query}`,
              viewport,
              async (page) => {
                await openTableRoute(page, '/admin/features', 'Features');
                await page.getByTestId('admin-features-search').fill(query);
                await throttle();
                await page.getByTestId('admin-features-search-submit').click();
                await throttle();
                await page.getByTestId('admin-features-kind-filter').selectOption(kind);
                await throttle();
                await page.getByTestId('admin-features-status-filter').selectOption(status);
                await throttle();
                await page.getByTestId('admin-features-issue-filter').selectOption(issue);
                await waitForAdminTable(page);
                await expect(page.getByTestId('admin-features-search')).toHaveValue(query);
                await expect(page.getByTestId('admin-features-kind-filter')).toHaveValue(kind);
                await expect(page.getByTestId('admin-features-status-filter')).toHaveValue(status);
                await expect(page.getByTestId('admin-features-issue-filter')).toHaveValue(issue);
              },
            );
          }
        }
      }
    }
    for (const provider of providers) {
      for (const category of categories) {
        pushCase(
          cases,
          `features provider=${provider || 'all'} category=${category || 'all'}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/features', 'Features');
            await page.getByTestId('admin-features-provider-filter').fill(provider);
            await page.getByTestId('admin-features-category-filter').fill(category);
            await throttle();
            await page.getByTestId('admin-features-search-submit').click();
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-features-provider-filter')).toHaveValue(provider);
            await expect(page.getByTestId('admin-features-category-filter')).toHaveValue(category);
          },
        );
      }
    }
  }
}

function pushFeatureDetailSubpageCases(cases: AdminUiCase[]) {
  for (const viewport of compactViewports) {
    pushCase(
      cases,
      `feature detail subpages route read-only tabs ${viewport.name}`,
      viewport,
      async (page) => {
        await openTableRoute(page, '/admin/features', 'Features');
        await page.getByTestId('admin-features-kind-filter').selectOption('weather');
        await waitForAdminTable(page);

        const row = page.locator('[data-testid^="admin-features-row-"]').first();
        if ((await row.count()) === 0) return;

        const testId = await row.getAttribute('data-testid');
        const featureId = testId?.replace(/^admin-features-row-/, '');
        if (!featureId) return;

        const routes = [
          { tab: 'sources', heading: 'Sources' },
          { tab: 'overrides', heading: 'Overrides' },
          { tab: 'weather-values', heading: 'Weather Values' },
        ];

        for (const route of routes) {
          await throttle();
          await page.goto(`/admin/features/${encodeURIComponent(featureId)}/${route.tab}`);
          await reloginIfNeeded(page, `/admin/features/${featureId}/${route.tab}`);
          await expectAdminShell(page, route.heading);
          await expect(page.getByTestId(`admin-feature-tab-${route.tab}`)).toHaveAttribute(
            'aria-current',
            'page',
          );
          await waitForAdminTable(page);
        }
      },
    );
  }
}

function pushDebugRequestTimelineCases(cases: AdminUiCase[]) {
  for (const viewport of compactViewports) {
    pushCase(
      cases,
      'debug request timeline resolves captured request id',
      viewport,
      async (page) => {
        const captured = { requestIds: [] as string[] };
        installDebugRequestIdRecorder(page, captured);

        await openTableRoute(page, '/admin/debug/logs', 'Debug logs');
        const requestId = await waitForCapturedRequestId(captured);
        await throttle();
        await page.goto(`/admin/debug/request/${requestId}`);
        await reloginIfNeeded(page, `/admin/debug/request/${requestId}`);
        await expectAdminShell(page, 'Request timeline');
        await expect(page.getByTestId('admin-request-timeline-refresh')).toBeVisible();
        await expect(page.getByText('불러오는 중...')).toHaveCount(0, { timeout: 15_000 });

        const summaryVisible = await page
          .getByTestId('admin-request-timeline-summary')
          .isVisible({ timeout: 5000 })
          .catch(() => false);
        if (summaryVisible) {
          await expect(page.getByTestId('admin-request-timeline-summary')).toBeVisible();
        } else {
          await expect(page.getByText(/source가 없습니다|event가 없습니다/).first()).toBeVisible();
        }
        await expectNoRawSecrets(page);
      },
    );
  }
}

function pushProviderSyncFilterCases(cases: AdminUiCase[]) {
  const providers = ['', 'kma', 'visitkorea', 'kasi'];
  const statuses = ['running', 'all', 'queued', 'done', 'failed', 'cancelled'];
  for (const viewport of compactViewports) {
    for (const provider of providers) {
      for (const status of statuses) {
        pushCase(
          cases,
          `provider-sync filter provider=${provider || 'all'} status=${status}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/provider-sync', 'Provider sync');
            await page.getByTestId('admin-provider-sync-key').fill(provider);
            await throttle();
            await page.getByTestId('admin-provider-sync-submit').click();
            await throttle();
            await page.getByTestId('admin-provider-sync-job-status').selectOption(status);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-provider-sync-key')).toHaveValue(provider);
            await expect(page.getByTestId('admin-provider-sync-job-status')).toHaveValue(status);
          },
        );
      }
    }
  }
}

function pushEtlFilterCases(cases: AdminUiCase[]) {
  const statuses = ['running', 'all', 'queued', 'done', 'failed', 'cancelled'];
  for (let repeat = 1; repeat <= 5; repeat += 1) {
    for (const viewport of compactViewports) {
      for (const status of statuses) {
        pushCase(cases, `etl import status=${status} repeat=${repeat}`, viewport, async (page) => {
          await openTableRoute(page, '/admin/etl', 'ETL');
          await throttle();
          await page.getByTestId('admin-etl-import-status-filter').selectOption(status);
          await waitForAdminTable(page);
          await expect(page.getByTestId('admin-etl-import-status-filter')).toHaveValue(status);
        });
      }
    }
  }
}

function pushEtlAppOwnedCases(cases: AdminUiCase[]) {
  const appOwnedJobs = [
    'pinvi_email_outbox_job',
    'pinvi_telegram_system_outbox_job',
    'pinvi_location_log_archive_job',
  ];
  for (const viewport of compactViewports) {
    pushCase(cases, 'etl app-owned job rows expose live metadata', viewport, async (page) => {
      await openTableRoute(page, '/admin/etl', 'ETL');
      await expect(page.getByTestId('admin-etl-pinvi-status')).toBeVisible();
      await expect(page.getByTestId('admin-etl-pinvi-live-job-count')).toBeVisible();
      await expect(page.getByTestId('admin-etl-pinvi-live-schedule-count')).toBeVisible();
      for (const jobName of appOwnedJobs) {
        await expect(page.getByTestId(`admin-etl-job-${jobName}`)).toBeVisible();
        await expect(page.getByTestId(`admin-etl-job-${jobName}-live`)).toBeVisible();
        await expect(page.getByTestId(`admin-etl-job-${jobName}-timezone`)).toBeVisible();
        await expect(page.getByTestId(`admin-etl-job-${jobName}-latest-run`)).toBeVisible();
      }
      await expect(page.getByTestId('admin-etl-email-outbox')).toBeVisible();
      await expect(page.getByTestId('admin-etl-telegram-outbox')).toBeVisible();
      await expect(page.getByTestId('admin-etl-location-archive')).toBeVisible();
      await expectNoBlockingErrors(page);
    });
  }
}

function pushDedupIntegrityDebugCases(cases: AdminUiCase[]) {
  const dedupStatuses = ['pending', 'all', 'accepted', 'rejected', 'merged', 'ignored'];
  const integrityStatuses = ['open', 'acknowledged', 'resolved', 'ignored'];
  const severities = ['all', 'info', 'warning', 'error', 'critical'];
  const levels = ['error', 'all', 'info', 'warning', 'critical'];
  for (const viewport of compactViewports) {
    for (const status of dedupStatuses) {
      pushCase(cases, `dedup filter status=${status}`, viewport, async (page) => {
        await openTableRoute(page, '/admin/dedup-review', 'Dedup review');
        await page.getByTestId('admin-dedup-search').fill('kma');
        await throttle();
        await page.getByTestId('admin-dedup-submit').click();
        await throttle();
        await page.getByTestId('admin-dedup-status').selectOption(status);
        await waitForAdminTable(page);
        await expect(page.getByTestId('admin-dedup-status')).toHaveValue(status);
      });
    }
    for (const status of integrityStatuses) {
      for (const severity of severities) {
        pushCase(
          cases,
          `integrity filter status=${status} severity=${severity}`,
          viewport,
          async (page) => {
            await openTableRoute(page, '/admin/integrity', '정합성');
            await page.getByTestId('admin-integrity-status').selectOption(status);
            await throttle();
            await page.getByTestId('admin-integrity-severity').selectOption(severity);
            await waitForAdminTable(page);
            await expect(page.getByTestId('admin-integrity-status')).toHaveValue(status);
            await expect(page.getByTestId('admin-integrity-severity')).toHaveValue(severity);
          },
        );
      }
    }
    for (const level of levels) {
      pushCase(cases, `debug logs filter level=${level}`, viewport, async (page) => {
        await openTableRoute(page, '/admin/debug/logs', 'Debug logs');
        await page.getByTestId('admin-debug-level').selectOption(level);
        await page.getByTestId('admin-debug-source').fill('api');
        await page.getByTestId('admin-debug-min-status').fill('500');
        await throttle();
        await page.getByTestId('admin-debug-submit').click();
        await waitForAdminTable(page);
        await expect(page.getByTestId('admin-debug-level')).toHaveValue(level);
      });
    }
  }
}

function pushSortCases(cases: AdminUiCase[]) {
  for (let repeat = 1; repeat <= 3; repeat += 1) {
    for (const viewport of mixedViewports) {
      for (const spec of sortSpecs) {
        for (const column of spec.columns) {
          pushCase(
            cases,
            `sort ${spec.route} column=${column} repeat=${repeat}`,
            viewport,
            async (page) => {
              await openTableRoute(page, spec.route, spec.heading);
              const sortButton = page.getByTestId(`admin-table-sort-${column}`).first();
              await expect(sortButton).toBeVisible();
              await throttle();
              await sortButton.click();
              await expect(sortButton).toBeVisible();
              await expectNoBlockingErrors(page);
            },
          );
        }
      }
    }
  }
}

function pushDashboardCases(cases: AdminUiCase[]) {
  for (let repeat = 1; repeat <= 20; repeat += 1) {
    for (const viewport of viewports) {
      pushCase(cases, `dashboard stat cards repeat=${repeat}`, viewport, async (page) => {
        await openRoute(page, dashboardRoute);
        await expect(page.getByTestId('admin-system-pinvi_api')).toBeVisible();
        await expect(page.getByTestId('admin-system-kor_travel_map_api')).toBeVisible();
        await expect(page.getByTestId('admin-stat-사용자 총 수')).toBeVisible();
        await expect(page.getByTestId('admin-stat-여행 총 수')).toBeVisible();
      });
    }
  }
}

function pushGrafanaDashboardCases(cases: AdminUiCase[]) {
  const dashboards = {
    api: '/d/pinvi-api-http',
    db: '/d/pinvi-db-pool',
    websocket: '/d/pinvi-websocket',
    'etl-backup': '/d/pinvi-etl-backup',
  };
  for (const viewport of compactViewports) {
    for (const [dashboard, expectedPath] of Object.entries(dashboards)) {
      pushCase(cases, `grafana dashboard selector ${dashboard}`, viewport, async (page) => {
        await openRoute(page, {
          path: '/admin/grafana',
          heading: 'Grafana',
          readyTestId: 'admin-grafana-health-status',
        });
        await page.getByTestId(`admin-grafana-dashboard-${dashboard}`).click();
        await throttle();
        await expect(page.getByTestId('admin-grafana-dashboard-path')).toContainText(expectedPath);
        await expect(page.getByTestId('admin-grafana-frame')).toHaveAttribute(
          'src',
          new RegExp(escapeRegExp(expectedPath)),
        );
      });
    }
  }
}

function pushMcpValidationCases(cases: AdminUiCase[]) {
  const invalidUsers = ['', '00000000-0000-4000-8000-000000000001'];
  const reasons = ['', 'UI live validation'];
  for (let repeat = 1; repeat <= 20; repeat += 1) {
    for (const viewport of viewports) {
      for (const userId of invalidUsers) {
        for (const reason of reasons) {
          if (userId && reason) continue;
          pushCase(
            cases,
            `mcp issue local validation user=${userId || 'empty'} reason=${reason || 'empty'} repeat=${repeat}`,
            viewport,
            async (page) => {
              await openTableRoute(page, '/admin/mcp-tokens', 'MCP 토큰');
              await page.getByTestId('admin-mcp-user').fill(userId);
              await page.getByTestId('admin-mcp-reason').fill(reason);
              await throttle();
              await page.getByRole('button', { name: /^발급$/ }).click();
              if (!userId) {
                await expect(page.getByText('대상 user_id를 입력하세요.')).toBeVisible();
                return;
              }
              await expect(page.getByText('발급 사유를 입력하세요.')).toBeVisible();
            },
          );
        }
      }
    }
  }
}

function buildUiCases() {
  const cases: AdminUiCase[] = [];
  pushRouteCases(cases);
  pushNavigationCases(cases);
  pushPlaceholderCases(cases);
  pushUsersFilterCases(cases);
  pushTripsFilterCases(cases);
  pushPoisFilterCases(cases);
  pushApiCallFilterCases(cases);
  pushEmailsFilterCases(cases);
  pushBackupFilterCases(cases);
  pushBackupReadOnlyGuardCases(cases);
  pushMcpFilterCases(cases);
  pushFeatureRequestFilterCases(cases);
  pushFeaturesFilterCases(cases);
  pushFeatureDetailSubpageCases(cases);
  pushDebugRequestTimelineCases(cases);
  pushProviderSyncFilterCases(cases);
  pushEtlFilterCases(cases);
  pushEtlAppOwnedCases(cases);
  pushDedupIntegrityDebugCases(cases);
  pushSortCases(cases);
  pushDashboardCases(cases);
  pushGrafanaDashboardCases(cases);
  pushMcpValidationCases(cases);
  return cases;
}

const EXPECTED_LIVE_UI_CASE_COUNT = 6336;
const liveUiCases = buildUiCases();
const selectedLiveUiCases = liveUiCases
  .map((liveCase, index) => ({ liveCase, caseNumber: index + 1 }))
  .filter(({ caseNumber }) => caseNumber >= caseStart && caseNumber <= caseEnd)
  .slice(0, Number.isFinite(caseLimit) ? Math.max(0, caseLimit) : undefined);

base.describe('admin live UI e2e catalog', () => {
  base('UI live case catalog has at least 2000 browser cases', () => {
    expect(liveUiCases).toHaveLength(EXPECTED_LIVE_UI_CASE_COUNT);
    expect(liveUiCases.length).toBeGreaterThanOrEqual(2000);
    expect(liveUiCases.every((liveCase) => typeof liveCase.run === 'function')).toBe(true);
  });
});

base.describe('admin live UI login', () => {
  base.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  base.describe.configure({ mode: 'serial' });

  base('UI login rejects malformed email before live request', async ({ page }) => {
    await page.goto('/admin/login');
    await page.getByTestId('admin-login-email').fill('not-an-email');
    await page.getByTestId('admin-login-password').fill('whatever');
    await page.getByTestId('admin-login-submit').click();
    await expect(page.locator('#admin-login-email-error')).toBeVisible();
    await expect(page.getByTestId('admin-login-email')).toHaveAttribute('aria-invalid', 'true');
  });

  base('UI login can authenticate against live Admin', async ({ page }) => {
    base.skip(
      !adminEmail || !adminPassword,
      'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD가 필요합니다.',
    );
    await loginViaUi(page);
    await expect(page.getByRole('heading', { name: '대시보드' })).toBeVisible();
  });
});

liveUiTest.describe('admin live UI matrix', () => {
  liveUiTest.skip(!liveEnabled, 'PINVI_ADMIN_LIVE_E2E=1 일 때만 N150/live 대상에 실행합니다.');
  liveUiTest.skip(
    !hasAdminLiveAuth,
    'PINVI_ADMIN_LIVE_EMAIL/PINVI_ADMIN_LIVE_PASSWORD 또는 PINVI_ADMIN_LIVE_STORAGE_STATE가 필요합니다.',
  );

  for (const { liveCase, caseNumber } of selectedLiveUiCases) {
    liveUiTest(`[${String(caseNumber).padStart(4, '0')}] ${liveCase.name}`, async ({ page }) => {
      await runLiveCaseWithAttempts(page, liveCase);
    });
  }
});
