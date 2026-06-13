import { expect, test } from '@playwright/test';

const tripId = '11111111-1111-4111-8111-111111111111';
const userId = '22222222-2222-4222-8222-222222222222';
const attachmentId = '66666666-6666-4666-8666-666666666666';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

const TRIP_VIEW = {
  trip: {
    trip_id: tripId,
    owner_user_id: userId,
    title: '첨부 테스트 여행',
    description: null,
    region_hint: null,
    primary_region_code: null,
    primary_region_source: null,
    start_date: null,
    end_date: null,
    visibility: 'private',
    status: 'draft',
    version: 1,
    created_at: '2026-06-01T09:00:00+09:00',
    updated_at: '2026-06-01T09:00:00+09:00',
  },
  days: [],
  companions: [],
  share_links: [],
  broken_feature_count: 0,
};

const ATTACHMENT = {
  attachment_id: attachmentId,
  trip_id: tripId,
  trip_poi_id: null,
  source_attachment_id: null,
  bucket: 'pinvi-media',
  storage_key: 'user-uploads/trip_attachment/u/2026/06/photo.jpg',
  original_filename: 'photo.jpg',
  content_type: 'image/jpeg',
  byte_size: 5,
  public_url: null,
  role: 'image',
  description: null,
  sort_order: 0,
  created_at: '2026-06-01T09:00:00+09:00',
  updated_at: '2026-06-01T09:00:00+09:00',
};

test('첨부 업로드: presigned PUT 후 목록에 파일이 나타난다', async ({ page }) => {
  let uploaded = false;

  await page.route(/.*\/auth\/me$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { user_id: userId } }),
    });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}\/comments(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  // 첨부 GET/POST 를 한 라우트에서 메서드로 분기(POST 후 GET 은 업로드된 파일 반환).
  await page.route(/.*\/trips\/[0-9a-f-]{36}\/attachments$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    if (request.method() === 'POST') {
      uploaded = true;
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: ATTACHMENT }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: uploaded ? [ATTACHMENT] : [] }),
    });
  });

  await page.route(/.*\/trips\/[0-9a-f-]{36}$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: TRIP_VIEW }),
    });
  });

  await page.route(/.*\/storage\/upload-urls$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          method: 'PUT',
          bucket: 'pinvi-media',
          storage_key: ATTACHMENT.storage_key,
          upload_url: 'http://127.0.0.1:9555/pinvi-media/photo.jpg?X-Amz-Signature=z',
          headers: { 'Content-Type': 'image/jpeg' },
          expires_at: '2026-06-01T09:15:00+09:00',
          max_upload_bytes: 10485760,
          public_url: null,
        },
      }),
    });
  });

  // 브라우저 → RustFS presigned PUT 가로채기.
  await page.route(/.*127\.0\.0\.1:9555.*/, async (route) => {
    await route.fulfill({ status: 200, body: '' });
  });

  await page.goto(`/trips/${tripId}`);

  await expect(page.getByRole('heading', { name: '첨부 테스트 여행' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '첨부', exact: true })).toBeVisible();

  await page.getByTestId('attachment-input').setInputFiles({
    name: 'photo.jpg',
    mimeType: 'image/jpeg',
    buffer: Buffer.from('hello'),
  });

  await expect(page.getByTestId('trip-attachment-list')).toContainText('photo.jpg');
});
