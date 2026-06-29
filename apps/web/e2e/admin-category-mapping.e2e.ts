import { expect, test } from '@playwright/test';
import type { AdminCategoryMappingsResponse } from '@pinvi/schemas';

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

type CategoryOverrideUpdateBody = {
  display_name_ko: string;
  marker_color: string;
  marker_icon: string;
  access_reason: string;
};

const baseCategoryMappings: AdminCategoryMappingsResponse = {
  source_of_truth: 'kor-travel-map:/v1/categories',
  mode: 'pinvi_override',
  include_counts: true,
  active_only: false,
  total_count: 2,
  filtered_count: 2,
  active_count: 1,
  inactive_count: 1,
  db_feature_total: 15,
  override_count: 1,
  items: [
    {
      code: '01070100',
      label: '해수욕장',
      upstream_label: '해수욕장',
      parent_code: '010701',
      depth: 3,
      path: ['자연', '해안', '해수욕장'],
      maki_icon: 'swimming',
      upstream_maki_icon: 'swimming',
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
      display_name_ko: '부산 해수욕장',
      marker_color: 'P-03',
      marker_icon: 'beach',
      effective_label: '부산 해수욕장',
      effective_marker_color: 'P-03',
      effective_maki_icon: 'beach',
      has_override: true,
      override_updated_at: '2026-06-29T09:00:00+09:00',
      override_updated_by_user_id: '77777777-7777-4777-8777-777777777777',
    },
    {
      code: '99990000',
      label: '새 카테고리',
      upstream_label: '새 카테고리',
      parent_code: null,
      depth: 1,
      path: ['새 카테고리'],
      maki_icon: 'marker',
      upstream_maki_icon: 'marker',
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
      display_name_ko: null,
      marker_color: null,
      marker_icon: null,
      effective_label: '새 카테고리',
      effective_marker_color: null,
      effective_maki_icon: 'marker',
      has_override: false,
      override_updated_at: null,
      override_updated_by_user_id: null,
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
  const categoryMappings = structuredClone(baseCategoryMappings);
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
  await expect(page.getByTestId('admin-category-row-01070100')).toContainText('부산 해수욕장');
  await expect(page.getByTestId('admin-category-row-01070100')).toContainText('override');
  await expect(page.getByTestId('admin-category-row-99990000')).toContainText('fallback');
  await expect(page.getByTestId('admin-category-summary')).toContainText(
    'kor-travel-map:/v1/categories',
  );
  await expect(page.getByTestId('admin-category-summary')).toContainText('override');
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

test('Category mapping override 저장과 rollback 요청을 보낸다', async ({ page }) => {
  const categoryMappings = structuredClone(baseCategoryMappings);
  let patchBody: CategoryOverrideUpdateBody | null = null;
  let deleteBody: { access_reason: string } | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/category-mappings',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: categoryMappings }),
      });
    },
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/category-mappings/01070100',
    async (route) => {
      const request = route.request();
      if (request.method() === 'PATCH') {
        const body = request.postDataJSON() as CategoryOverrideUpdateBody;
        patchBody = body;
        const item = categoryMappings.items[0]!;
        categoryMappings.items[0] = {
          ...item,
          display_name_ko: body.display_name_ko,
          marker_color: body.marker_color,
          marker_icon: body.marker_icon,
          effective_label: body.display_name_ko,
          effective_marker_color: body.marker_color,
          effective_maki_icon: body.marker_icon,
          has_override: true,
        };
      } else if (request.method() === 'DELETE') {
        deleteBody = request.postDataJSON() as { access_reason: string };
        const item = categoryMappings.items[0]!;
        categoryMappings.items[0] = {
          ...item,
          display_name_ko: null,
          marker_color: null,
          marker_icon: null,
          effective_label: item.label,
          effective_marker_color: null,
          effective_maki_icon: item.maki_icon,
          has_override: false,
        };
        categoryMappings.override_count = 0;
      }
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: categoryMappings.items[0] }),
      });
    },
  );

  await page.goto('/admin/category-mapping');
  await page.getByTestId('admin-category-edit-01070100').click();
  await expect(page.getByTestId('admin-category-editor')).toBeVisible();

  await page.getByTestId('admin-category-display-name').fill('테스트 해변');
  await page.getByTestId('admin-category-marker-icon').fill('park');
  await page.getByTestId('admin-category-color-P-04').click();
  await page.getByTestId('admin-category-access-reason').fill('운영 팔레트 정정');
  await page.getByTestId('admin-category-save').click();
  await expect(page.getByTestId('admin-category-mutation-status')).toContainText(
    'override 저장 완료',
  );
  expect(patchBody).toEqual({
    display_name_ko: '테스트 해변',
    marker_color: 'P-04',
    marker_icon: 'park',
    access_reason: '운영 팔레트 정정',
  });

  await page.getByTestId('admin-category-access-reason').fill('override 원복');
  await page.getByTestId('admin-category-rollback').click();
  await expect(page.getByTestId('admin-category-mutation-status')).toContainText(
    'override rollback 완료',
  );
  expect(deleteBody).toEqual({ access_reason: 'override 원복' });
});
