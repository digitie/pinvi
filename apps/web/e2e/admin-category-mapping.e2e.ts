import { expect, test } from '@playwright/test';

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

const categoryMappings = {
  source_of_truth: 'kor-travel-map:/v1/categories',
  mode: 'read_only',
  include_counts: true,
  active_only: false,
  total_count: 2,
  filtered_count: 2,
  active_count: 1,
  inactive_count: 1,
  db_feature_total: 15,
  items: [
    {
      code: '01070100',
      label: '해수욕장',
      parent_code: '010701',
      depth: 3,
      path: ['자연', '해안', '해수욕장'],
      maki_icon: 'swimming',
      is_active: true,
      sort_order: 5,
      tier1_code: '01',
      tier1_name: '자연',
      tier2_code: '0107',
      tier2_name: '해안',
      tier3_code: '010701',
      tier3_name: '해수욕',
      tier4_code: '01070100',
      tier4_name: '해수욕장',
      db_active: true,
      db_feature_count: 12,
    },
    {
      code: '99990000',
      label: '새 카테고리',
      parent_code: null,
      depth: 1,
      path: ['새 카테고리'],
      maki_icon: 'marker',
      is_active: false,
      sort_order: 99,
      tier1_code: '99',
      tier1_name: '새 카테고리',
      tier2_code: null,
      tier2_name: null,
      tier3_code: null,
      tier3_name: null,
      tier4_code: null,
      tier4_name: null,
      db_active: false,
      db_feature_count: 3,
    },
  ],
};

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

test('Category mapping 페이지가 upstream catalog와 Pinvi marker preview를 표시한다', async ({
  page,
}) => {
  const seenUrls: string[] = [];
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/category-mappings',
    async (route) => {
      seenUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: categoryMappings }),
      });
    },
  );

  await page.goto('/admin/category-mapping');
  await expect(page.getByRole('heading', { name: '카테고리 매핑' })).toBeVisible();
  await expect(page.getByTestId('admin-category-row-01070100')).toBeVisible();
  await expect(page.getByTestId('admin-category-row-99990000')).toContainText('fallback');
  await expect(page.getByTestId('admin-category-summary')).toContainText(
    'kor-travel-map:/v1/categories',
  );
  await expect(page.getByTestId('admin-category-summary')).toContainText('fallback');

  await page.getByTestId('admin-category-search').fill('해수');
  await page.getByTestId('admin-category-counts').uncheck();
  await page.getByTestId('admin-category-active').selectOption('active');
  await page.getByTestId('admin-category-submit').click();
  await expect(page.getByTestId('admin-category-row-01070100')).toBeVisible();

  const lastUrl = new URL(seenUrls[seenUrls.length - 1]!);
  expect(lastUrl.searchParams.get('q')).toBe('해수');
  expect(lastUrl.searchParams.get('include_counts')).toBe('false');
  expect(lastUrl.searchParams.get('active_only')).toBe('true');
});
