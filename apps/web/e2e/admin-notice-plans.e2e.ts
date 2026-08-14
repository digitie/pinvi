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

function canonicalImportResult(overrides: Record<string, unknown> = {}) {
  return {
    notice_plan_id: planId,
    created_plan: true,
    not_modified: false,
    source_system: 'kor-travel-map',
    source_curation_collection_id: '44444444-4444-4444-8444-444444444444',
    source_curation_collection_revision: '7',
    source_curation_collection_etag:
      '"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"',
    source_curation_item_set_hash_version: 'ktm-db-item-set-v1',
    source_curation_item_set_hash:
      'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    source_curation_item_count: 2,
    copied_poi_count: 2,
    removed_poi_count: 0,
    ...overrides,
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

test('Admin이 canonical collection import의 idempotency와 오류 복구를 제어한다', async ({
  page,
}) => {
  const importRequests: Array<{ body: Record<string, unknown>; idempotencyKey: string | null }> =
    [];
  let importAttempt = 0;
  await page.route(
    (url) =>
      url.port === '12801' &&
      (url.pathname === '/admin/notice-plans' ||
        url.pathname === '/admin/notice-plans/imports/kor-travel-map-curation-collections'),
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === '/admin/notice-plans' && request.method() === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: [basePlan()] }),
        });
        return;
      }
      if (
        path === '/admin/notice-plans/imports/kor-travel-map-curation-collections' &&
        request.method() === 'POST'
      ) {
        importRequests.push({
          body: request.postDataJSON() as Record<string, unknown>,
          idempotencyKey: request.headers()['idempotency-key'] ?? null,
        });
        importAttempt += 1;
        if (importAttempt === 1) {
          await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify({
              data: canonicalImportResult({ not_modified: false, created_plan: true }),
            }),
          });
          return;
        }
        if (importAttempt === 2 || importAttempt === 3) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              data: canonicalImportResult({ not_modified: true, created_plan: false }),
            }),
          });
          return;
        }
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: {
              code: 'CURATION_COLLECTION_IMPORT_CONFLICT',
              message: 'snapshot이 달라졌습니다.',
            },
          }),
        });
      }
    },
  );

  await page.goto('/admin/notice-plans');
  await page
    .getByTestId('admin-notice-canonical-import-collection-id')
    .fill('44444444-4444-4444-8444-444444444444');
  await page.getByTestId('admin-notice-canonical-import-published').selectOption('published');
  await page.getByTestId('admin-notice-canonical-import-submit').click();

  await expect(page.getByTestId('admin-notice-canonical-import-result')).toContainText(
    '새 추천 여행을 만들었습니다.',
  );
  expect(importRequests).toHaveLength(1);
  expect(importRequests[0]?.body).toEqual({
    collection_id: '44444444-4444-4444-8444-444444444444',
    mode: 'create',
    is_published: true,
  });
  expect(importRequests[0]?.idempotencyKey).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
  );

  // create 뒤 refresh로 전환한 뒤의 반영은 replay가 아니라 새 Map snapshot을 읽어야 한다.
  await page.getByTestId('admin-notice-canonical-import-mode').selectOption('refresh');
  await page.getByTestId('admin-notice-canonical-import-submit').click();
  await expect.poll(() => importRequests).toHaveLength(2);
  expect(importRequests[1]?.idempotencyKey).not.toBe(importRequests[0]?.idempotencyKey);
  expect(importRequests[1]?.body).toMatchObject({ mode: 'refresh' });
  await expect(page.getByTestId('admin-notice-canonical-import-result')).toContainText(
    'Map snapshot이 변경되지 않아',
  );

  // 같은 refresh를 다시 실행해도 terminal command key는 재사용하지 않는다.
  await page.getByTestId('admin-notice-canonical-import-submit').click();
  await expect.poll(() => importRequests).toHaveLength(3);
  expect(importRequests[2]?.idempotencyKey).not.toBe(importRequests[1]?.idempotencyKey);

  await page
    .getByTestId('admin-notice-canonical-import-collection-id')
    .fill('55555555-5555-4555-8555-555555555555');
  await page.getByTestId('admin-notice-canonical-import-submit').click();
  await expect(page.getByTestId('admin-notice-canonical-import-error')).toContainText(
    '입력을 확인한 뒤 새 요청으로 다시 실행하세요.',
  );
  expect(importRequests).toHaveLength(4);
  expect(importRequests[3]?.idempotencyKey).not.toBe(importRequests[2]?.idempotencyKey);
  await expect(page.getByTestId('admin-notice-canonical-import-retry')).toHaveCount(0);

  // terminal 409도 새 명령으로만 다시 시도한다.
  const conflictKey = importRequests[3]?.idempotencyKey;
  await page.getByTestId('admin-notice-canonical-import-submit').click();
  await expect.poll(() => importRequests).toHaveLength(5);
  expect(importRequests[4]?.idempotencyKey).not.toBe(conflictKey);
});

test('Admin UI는 Map canonical plan과 POI의 source-derived 작업을 노출하지 않는다', async ({
  page,
}) => {
  const canonicalPoi = {
    ...basePoi(),
    source_curation_item_id: '66666666-6666-4666-8666-666666666666',
  };
  let plan = {
    ...basePlan(),
    source_system: 'kor-travel-map' as const,
    pois: [canonicalPoi],
  };
  let patchBody: Record<string, unknown> | null = null;

  await page.route(
    (url) => url.port === '12801' && url.pathname.startsWith('/admin/notice-plans'),
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === `/admin/notice-plans/${planId}` && request.method() === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: plan }),
        });
        return;
      }
      if (path === '/admin/notice-plans' && request.method() === 'GET') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: [plan] }),
        });
        return;
      }
      if (path === `/admin/notice-plans/${planId}` && request.method() === 'PATCH') {
        patchBody = request.postDataJSON() as Record<string, unknown>;
        expect(patchBody).toEqual({ is_published: true });
        plan = { ...plan, is_published: true, version: plan.version + 1 };
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: plan }),
        });
        return;
      }
      await route.fulfill({ status: 404, body: JSON.stringify({ detail: 'mock' }) });
    },
  );

  await page.goto(`/admin/notice-plans/${planId}`);
  await expect(page.getByTestId('admin-notice-title')).toBeDisabled();
  await expect(page.getByTestId('admin-notice-category')).toBeDisabled();
  await expect(page.getByTestId('admin-notice-destination')).toBeDisabled();
  await expect(page.getByRole('button', { name: '삭제' })).toHaveCount(0);
  await expect(page.getByTestId(`admin-notice-poi-edit-${poiId}`)).toHaveCount(0);
  await expect(page.getByText('Map refresh 관리')).toBeVisible();
  await expect(page.getByTestId('admin-notice-poi-add')).toBeVisible();

  await page.getByTestId('admin-notice-published').check();
  await page.getByTestId('admin-notice-save').click();
  await expect.poll(() => patchBody).toEqual({ is_published: true });
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
