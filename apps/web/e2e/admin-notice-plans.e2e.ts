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

const planId = '11111111-1111-4111-8111-111111111111';
const poiId = '22222222-2222-4222-8222-222222222222';
const attachmentId = '33333333-3333-4333-8333-333333333333';

function basePlan() {
  return {
    notice_plan_id: planId,
    slug: 'seoul-cafe',
    title: '서울 카페 산책',
    category: 'cafe',
    summary: '성수와 한남을 잇는 반나절 코스',
    source_name: 'Pinvi',
    destination: '서울',
    starts_on: '2026-07-01',
    ends_on: '2026-07-02',
    is_published: false,
    version: 1,
    created_at: '2026-06-29T09:00:00+09:00',
    updated_at: '2026-06-29T09:00:00+09:00',
    pois: [] as ReturnType<typeof basePoi>[],
  };
}

function basePoi() {
  return {
    notice_poi_id: poiId,
    notice_plan_id: planId,
    day_index: 1,
    sort_order: '001000',
    feature_id: null,
    feature_snapshot: { display_name: '성수 카페' },
    memo: '오후 방문',
    budget_amount: '12000',
    currency: 'KRW',
    user_url: null,
    custom_marker_color: null,
    custom_marker_icon: null,
    version: 1,
    created_at: '2026-06-29T09:00:00+09:00',
    updated_at: '2026-06-29T09:00:00+09:00',
  };
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

test('Admin notice plan 목록이 필터와 편집 링크를 제공한다', async ({ page }) => {
  const seenUrls: string[] = [];
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/notice-plans',
    async (route) => {
      seenUrls.push(route.request().url());
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: [basePlan()] }),
      });
    },
  );

  await page.goto('/admin/notice-plans');
  await expect(page.getByRole('heading', { name: '추천 여행' })).toBeVisible();
  await expect(page.getByTestId(`admin-notice-row-${planId}`)).toContainText('서울 카페 산책');

  await page.getByTestId('admin-notice-search').fill('서울');
  await page.getByTestId('admin-notice-category-filter').fill('cafe');
  await page.getByTestId('admin-notice-published-filter').selectOption('false');
  await page.getByTestId('admin-notice-submit').click();

  const lastUrl = new URL(seenUrls[seenUrls.length - 1]!);
  expect(lastUrl.searchParams.get('q')).toBe('서울');
  expect(lastUrl.searchParams.get('category')).toBe('cafe');
  expect(lastUrl.searchParams.get('is_published')).toBe('false');
});

test('Admin notice plan 생성, 편집, POI 추가, 첨부 업로드를 수행한다', async ({ page }) => {
  let plan: ReturnType<typeof basePlan> = basePlan();
  let poi: ReturnType<typeof basePoi> = basePoi();
  let planAttachments: Record<string, unknown>[] = [];
  let createBody: Record<string, unknown> | null = null;
  let patchBody: Record<string, unknown> | null = null;
  let poiBody: Record<string, unknown> | null = null;
  let attachmentBody: Record<string, unknown> | null = null;
  let uploaded = false;

  await page.route(
    (url) => url.port === '12801' && url.pathname.startsWith('/admin/notice-plans'),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      const method = request.method();

      if (path === '/admin/notice-plans' && method === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: [plan] }),
        });
        return;
      }
      if (path === '/admin/notice-plans' && method === 'POST') {
        createBody = request.postDataJSON() as Record<string, unknown>;
        plan = {
          ...plan,
          ...(createBody as Partial<ReturnType<typeof basePlan>>),
          notice_plan_id: planId,
          version: 1,
          pois: [] as ReturnType<typeof basePoi>[],
        };
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: plan }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}` && method === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: plan }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}` && method === 'PATCH') {
        expect(request.headers()['if-match']).toBe(String(plan.version));
        patchBody = request.postDataJSON() as Record<string, unknown>;
        plan = {
          ...plan,
          ...(patchBody as Partial<ReturnType<typeof basePlan>>),
          version: plan.version + 1,
        };
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: plan }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}/pois` && method === 'POST') {
        poiBody = request.postDataJSON() as Record<string, unknown>;
        poi = {
          ...poi,
          ...(poiBody as Partial<ReturnType<typeof basePoi>>),
          notice_poi_id: poiId,
          notice_plan_id: planId,
          version: 1,
        };
        plan = { ...plan, pois: [poi], version: plan.version + 1 };
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: poi }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}/attachments` && method === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: planAttachments }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}/attachments` && method === 'POST') {
        attachmentBody = request.postDataJSON() as Record<string, unknown>;
        planAttachments = [
          {
            ...attachmentBody,
            attachment_id: attachmentId,
            trip_id: null,
            trip_day_index: null,
            trip_poi_id: null,
            curated_plan_id: planId,
            curated_poi_id: null,
            notice_plan_id: planId,
            notice_poi_id: null,
            source_attachment_id: null,
            description: null,
            public_url: null,
            created_at: '2026-06-29T09:05:00+09:00',
            updated_at: '2026-06-29T09:05:00+09:00',
          },
        ];
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: planAttachments[0]! }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}/pois/${poiId}/attachments` && method === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: [] }),
        });
        return;
      }

      await route.fulfill({
        status: 404,
        body: JSON.stringify({ error: { code: 'NOT_FOUND', message: 'mock' } }),
      });
    },
  );

  await page.route(
    (url) => url.port === '12801' && url.pathname === '/storage/upload-urls',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            method: 'PUT',
            bucket: 'pinvi-media',
            storage_key: `user-uploads/curated_plan_attachment/${adminUser.user_id}/2026/06/cover.jpg`,
            upload_url: 'http://127.0.0.1:9558/pinvi-media/cover.jpg?X-Amz-Signature=z',
            headers: { 'Content-Type': 'image/jpeg' },
            expires_at: '2026-06-29T09:15:00+09:00',
            max_upload_bytes: 10485760,
            public_url: null,
          },
        }),
      });
    },
  );
  await page.route(/.*127\.0\.0\.1:9558.*/, async (route) => {
    uploaded = true;
    await route.fulfill({ status: 200, body: '' });
  });

  await page.goto('/admin/notice-plans/new');
  await page.getByTestId('admin-notice-slug').fill('seoul-cafe');
  await page.getByTestId('admin-notice-title').fill('서울 카페 산책');
  await page.getByTestId('admin-notice-category').fill('cafe');
  await page.getByTestId('admin-notice-destination').fill('서울');
  await page.getByTestId('admin-notice-published').check();
  await page.getByTestId('admin-notice-save').click();

  await expect(page).toHaveURL(/\/admin\/notice-plans\/11111111-1111-4111-8111-111111111111$/);
  expect(createBody).toMatchObject({
    slug: 'seoul-cafe',
    title: '서울 카페 산책',
    category: 'cafe',
    destination: '서울',
    is_published: true,
  });

  await page.getByTestId('admin-notice-title').fill('서울 카페 큐레이션');
  await page.getByTestId('admin-notice-save').click();
  await expect(page.getByText('추천 여행을 저장했습니다.')).toBeVisible();
  expect(patchBody).toMatchObject({ title: '서울 카페 큐레이션' });

  await page.getByTestId('admin-notice-poi-feature').fill('feature::cafe::seongsu');
  await page.getByTestId('admin-notice-poi-memo').fill('오후 방문');
  await page.getByTestId('admin-notice-poi-add').click();
  await expect(page.getByTestId(`admin-notice-poi-row-${poiId}`)).toContainText('오후 방문');
  expect(poiBody).toMatchObject({
    feature_id: 'feature::cafe::seongsu',
    memo: '오후 방문',
  });

  await page.getByTestId('admin-notice-attachment-input').setInputFiles({
    name: 'cover.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('cover'),
  });
  await expect(page.getByTestId('admin-notice-attachments')).toContainText('cover.jpg');
  expect(uploaded).toBe(true);
  expect(attachmentBody).toMatchObject({
    bucket: 'pinvi-media',
    original_filename: 'cover.jpg',
    role: 'image',
  });
});
