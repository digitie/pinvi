import { expect, test } from '@playwright/test';
import type {
  AdminFeatureOverridesResponse,
  AdminFeatureSourcesResponse,
  AdminFeatureWeatherValuesResponse,
} from '@pinvi/schemas';

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

const sourcesResponse: AdminFeatureSourcesResponse = {
  feature_id: 'f_place_1',
  items: [
    {
      source_record_key: 'visitkorea:places:1',
      provider: 'visitkorea',
      dataset_key: 'places',
      source_entity_type: 'content',
      source_entity_id: '1',
      source_version: null,
      source_role: 'primary',
      match_method: 'natural_key',
      confidence: 100,
      is_primary_source: true,
      raw_name: '해운대 카페',
      raw_address: '부산 해운대구 해운대해변로',
      raw_longitude: 129.163,
      raw_latitude: 35.158,
      raw_payload_hash: 'sha256:abc',
      raw_data: { name: '해운대 카페' },
      fetched_at: '2026-06-11T00:00:00+09:00',
      imported_at: '2026-06-11T00:01:00+09:00',
      expires_at: null,
      linked_at: '2026-06-11T00:02:00+09:00',
    },
  ],
};

const overridesResponse: AdminFeatureOverridesResponse = {
  feature_id: 'f_place_1',
  items: [
    {
      override_id: 'ovr-1',
      source_record_key: 'visitkorea:places:1',
      field_path: 'detail.phone',
      source_value: '051-111-1111',
      override_value: '051-000-0000',
      prevent_provider_reactivation: true,
      status: 'active',
      reason: '운영 검수',
      created_by: 'pinvi-admin',
      created_at: '2026-06-12T00:10:00+09:00',
    },
  ],
};

const weatherValuesResponse: AdminFeatureWeatherValuesResponse = {
  feature_id: 'f_place_1',
  asof: '2026-06-12T10:00:00+09:00',
  latest_at: '2026-06-12T09:30:00+09:00',
  is_stale: false,
  source_styles: ['nowcast', 'short'],
  items: [
    {
      metric_key: 'T1H',
      metric_name: '기온',
      forecast_style: 'nowcast',
      timeline_bucket: 'current',
      valid_at: '2026-06-12T10:00:00+09:00',
      issued_at: null,
      observed_at: null,
      value_number: 24.5,
      value_text: null,
      unit: '℃',
      severity: 'normal',
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

test('Admin feature detail subpage가 deep link와 tab 상태를 처리한다', async ({ page }) => {
  const requests: string[] = [];

  await page.route(
    (url) => url.port === '12801' && url.pathname.startsWith('/admin/features/'),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      requests.push(route.request().url());

      if (pathname === '/admin/features/f_place_1/sources') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: sourcesResponse }),
        });
        return;
      }
      if (pathname === '/admin/features/f_place_1/overrides') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: overridesResponse }),
        });
        return;
      }
      if (pathname === '/admin/features/f_place_1/weather-values') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: weatherValuesResponse }),
        });
        return;
      }
      if (pathname === '/admin/features/empty_feature/sources') {
        await route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: { feature_id: 'empty_feature', items: [] } }),
        });
        return;
      }
      if (pathname === '/admin/features/bad_feature/overrides') {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'FEATURE_SERVICE_UNAVAILABLE',
              message: 'kor_travel_map admin 서비스가 일시적으로 사용 불가합니다.',
            },
          }),
        });
        return;
      }

      await route.fulfill({ status: 404, body: '{}' });
    },
  );

  await page.goto('/admin/features/f_place_1/sources');
  await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible();
  await expect(page.getByTestId('admin-feature-source-row-visitkorea:places:1')).toContainText(
    '해운대 카페',
  );

  await page.getByTestId('admin-feature-tab-overrides').click();
  await expect(page).toHaveURL(/\/admin\/features\/f_place_1\/overrides$/);
  await expect(page.getByTestId('admin-feature-override-row-ovr-1')).toContainText('detail.phone');

  await expect(page.getByTestId('admin-feature-tab-weather-values')).toHaveAttribute(
    'href',
    '/admin/features/f_place_1/weather-values',
  );
  await page.goto('/admin/features/f_place_1/weather-values');
  await expect(page).toHaveURL(/\/admin\/features\/f_place_1\/weather-values$/);
  await expect(page.getByTestId('admin-feature-weather-row-T1H')).toContainText('24.5');

  await page.goto('/admin/features/empty_feature/sources');
  await expect(page.getByText('source link가 없습니다.')).toBeVisible();

  await page.goto('/admin/features/bad_feature/overrides');
  await expect(page.getByTestId('admin-feature-tab-error')).toContainText('일시적으로 사용 불가');

  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});
