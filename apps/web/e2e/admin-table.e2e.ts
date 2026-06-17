import { type Page, expect, test } from '@playwright/test';

// AdminTable(@tanstack/react-table + react-virtual) 동작 세부 검증.
// /admin/users(비가상)로 헤더/정렬/empty/loading/sticky를, /admin/api-calls(가상)로 가상화를 본다.
// 주의: 응답은 ApiClient에서 Zod로 파싱되므로 user_id/request_id는 반드시 유효한 UUID여야 한다.

const adminUser = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

// 정렬 결정성을 위해 닉네임/가입일이 서로 다른 3행(목 순서: charlie, alice, bob).
const UID = {
  charlie: '11111111-1111-4111-8111-111111111111',
  alice: '22222222-2222-4222-8222-222222222222',
  bob: '33333333-3333-4333-8333-333333333333',
};

function userRow(id: string, nickname: string, createdAt: string) {
  return {
    user_id: id,
    email_masked: `${nickname}@example.com`,
    nickname,
    status: 'active',
    roles: ['user'],
    email_verified_at: '2026-06-01T09:00:00+09:00',
    created_at: createdAt,
  };
}

const THREE_USERS = [
  userRow(UID.charlie, 'charlie', '2026-03-01T00:00:00+09:00'),
  userRow(UID.alice, 'alice', '2026-01-01T00:00:00+09:00'),
  userRow(UID.bob, 'bob', '2026-02-01T00:00:00+09:00'),
];

const usersRowId = (uid: string) => `admin-users-row-${uid}`;

async function mockUsers(
  page: Page,
  items: ReturnType<typeof userRow>[],
  opts: { delayMs?: number } = {},
) {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/users',
    async (route) => {
      if (opts.delayMs) {
        await new Promise((resolve) => setTimeout(resolve, opts.delayMs));
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: { items, total: items.length, page: 1, limit: 50 },
        }),
      });
    },
  );
}

function rowOrder(page: Page) {
  return page
    .locator('tbody tr[data-testid^="admin-users-row-"]')
    .evaluateAll((trs) => trs.map((tr) => tr.getAttribute('data-testid')));
}

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: adminUser }),
      });
    },
  );
});

test('table/columnheader role과 정렬 가능 헤더(버튼)를 렌더한다', async ({ page }) => {
  await mockUsers(page, THREE_USERS);
  await page.goto('/admin/users');

  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByRole('columnheader', { name: /이메일/ })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: /닉네임/ })).toBeVisible();
  // 정렬 가능 컬럼은 헤더 버튼이 있고, roles 컬럼은 정렬 불가 → 버튼 없음
  await expect(page.getByTestId('admin-table-sort-nickname')).toBeVisible();
  await expect(page.getByTestId('admin-table-sort-roles')).toHaveCount(0);
});

test('헤더 클릭으로 asc→desc 정렬하고 aria-sort를 갱신한다', async ({ page }) => {
  await mockUsers(page, THREE_USERS);
  await page.goto('/admin/users');
  await expect(page.getByTestId(usersRowId(UID.alice))).toBeVisible();

  expect(await rowOrder(page)).toEqual([
    usersRowId(UID.charlie),
    usersRowId(UID.alice),
    usersRowId(UID.bob),
  ]);

  const nicknameHeader = page.getByRole('columnheader', { name: /닉네임/ });
  await page.getByTestId('admin-table-sort-nickname').click();
  expect(await rowOrder(page)).toEqual([
    usersRowId(UID.alice),
    usersRowId(UID.bob),
    usersRowId(UID.charlie),
  ]);
  await expect(nicknameHeader).toHaveAttribute('aria-sort', 'ascending');

  await page.getByTestId('admin-table-sort-nickname').click();
  expect(await rowOrder(page)).toEqual([
    usersRowId(UID.charlie),
    usersRowId(UID.bob),
    usersRowId(UID.alice),
  ]);
  await expect(nicknameHeader).toHaveAttribute('aria-sort', 'descending');
});

test('빈 목록은 안내 문구를 표시한다', async ({ page }) => {
  await mockUsers(page, []);
  await page.goto('/admin/users');
  await expect(page.getByText('항목이 없습니다.')).toBeVisible();
});

test('로딩 중에는 안내 문구를 보였다가 데이터로 대체된다', async ({ page }) => {
  await mockUsers(page, THREE_USERS, { delayMs: 1200 });
  await page.goto('/admin/users');
  await expect(page.getByText('불러오는 중...')).toBeVisible();
  await expect(page.getByTestId(usersRowId(UID.alice))).toBeVisible();
});

test('헤더는 sticky로 고정된다', async ({ page }) => {
  await mockUsers(page, THREE_USERS);
  await page.goto('/admin/users');
  await expect(page.getByRole('table')).toBeVisible();
  const position = await page
    .locator('thead')
    .first()
    .evaluate((el) => getComputedStyle(el).position);
  expect(position).toBe('sticky');
});

test('가상화: 큰 로그 목록은 보이는 행만 DOM에 두고 스크롤 시 후행을 렌더한다', async ({ page }) => {
  // request_id는 UUID여야 파싱을 통과한다(스키마 z.string().uuid()).
  const apiUuid = (i: number) => `00000000-0000-4000-8000-${String(i).padStart(12, '0')}`;
  const apiCallsRowId = (i: number) => `admin-api-calls-row-${apiUuid(i)}`;
  const many = Array.from({ length: 200 }, (_, i) => ({
    log_id: i,
    provider: 'kma',
    endpoint: `/weather/${i}`,
    status_code: 200,
    latency_ms: 10 + i,
    error_class: null,
    error_message: null,
    request_id: apiUuid(i),
    occurred_at: `2026-06-01T00:${String(Math.floor(i / 60)).padStart(2, '0')}:${String(i % 60).padStart(2, '0')}+09:00`,
  }));

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/api-calls',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: many }),
      });
    },
  );

  await page.goto('/admin/api-calls');
  await expect(page.getByTestId(apiCallsRowId(0))).toBeVisible();
  // 후행은 초기 윈도우에 없다(가상화).
  await expect(page.getByTestId(apiCallsRowId(190))).toHaveCount(0);

  // 가상 스크롤 컨테이너를 끝까지 스크롤 → 마지막 행이 렌더된다.
  await page.getByTestId('admin-table-scroll').evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await expect(page.getByTestId(apiCallsRowId(199))).toBeVisible();
});
