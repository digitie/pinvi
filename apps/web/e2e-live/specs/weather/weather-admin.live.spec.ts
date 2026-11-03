/**
 * WX — admin Weather Values page, read-only (WX-018, WX-019).
 * Facts (PinVi main 620b6046 / local a07257e7 identical for these files):
 *  - app/(admin)/admin/features/page.tsx: admin-features-search, admin-features-search-submit,
 *    admin-features-detail-{feature_id}, admin-features-link-weather-values.
 *  - app/(admin)/admin/features/[feature_id]/FeatureDetailSubpage.tsx: tab 'Weather Values', admin-feature-subpage,
 *    admin-feature-weather-refresh, rows admin-feature-weather-row-{metric_key}-…, empty 'weather 값이 없습니다.',
 *    error admin-feature-tab-error.
 *  - API: GET /admin/features/{id}/weather-values — kor-travel-weather direct regardless of the Map flag (§9 table).
 */
import { expect, test, type Page } from '@playwright/test';
import { loginAsAdmin, shot, waitForRequest } from '../../helpers/live';
import { annotate, onMobile } from '../../helpers/weather';

const WEATHER_VALUES_RE = /\/admin\/features\/[^/?]+\/weather-values(\?|$)/;

function writeGuard(page: Page): () => string[] {
  const writes: string[] = [];
  page.on('request', (req) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(req.method()) && /\/admin\//.test(req.url())) {
      writes.push(`${req.method()} ${new URL(req.url()).pathname}`);
    }
  });
  return () => writes;
}

async function openWeatherValues(page: Page): Promise<string> {
  await page.goto('/admin/features');
  await page.getByTestId('admin-features-search').fill('안동하회마을');
  await page.getByTestId('admin-features-search-submit').click();
  const detailBtn = page.locator('[data-testid^="admin-features-detail-"]').first();
  await expect(detailBtn).toBeVisible({ timeout: 20_000 });
  await detailBtn.click();
  const pending = waitForRequest(page, WEATHER_VALUES_RE);
  await page.getByTestId('admin-features-link-weather-values').click();
  const res = await pending;
  expect(res.status(), 'GET /admin/features/{id}/weather-values').toBe(200);
  await expect(page).toHaveURL(/\/admin\/features\/[^/]+\/weather-values/);
  return new URL(page.url()).pathname.split('/')[3]!;
}

async function expectTableOrEmpty(page: Page): Promise<number> {
  await expect(page.getByTestId('admin-feature-subpage')).toBeVisible();
  await expect(page.getByText('Weather Values').first()).toBeVisible();
  await expect(page.getByTestId('admin-feature-tab-error')).toHaveCount(0);
  const rows = page.locator('[data-testid^="admin-feature-weather-row-"]');
  const empty = page.getByText('weather 값이 없습니다.');
  await expect(rows.first().or(empty)).toBeVisible({ timeout: 20_000 });
  const n = await rows.count();
  if (n === 0) await expect(empty).toBeVisible();
  return n;
}

test.describe('weather · admin weather-values', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '관리자 UI는 데스크톱 전용');

  test('WX-018 읽기 전용: 표 또는 "값 없음", 오류 없음, 쓰기 요청 0건', async ({ page }) => {
    test.fail(true, '#648: /admin/features?q=<한국어> → 503 FEATURE_SERVICE_UNAVAILABLE');
    const writes = writeGuard(page);
    await loginAsAdmin(page);
    const featureId = await openWeatherValues(page);
    const n = await expectTableOrEmpty(page);
    const providers = n > 0 ? await page.locator('[data-testid^="admin-feature-weather-row-"]').allInnerTexts() : [];
    const providerSet = new Set(providers.flatMap((t) => t.match(/python-[a-z]+-api|openweathermap|weatherapi|open_meteo|wttr_in/g) ?? []));
    annotate(`feature=${featureId} rows=${n} providers=${[...providerSet].join(',')}`);
    expect(writes(), '읽기 전용 페이지에서 쓰기 요청 금지').toEqual([]);
    await shot(page, 'WX-018', 'weather-values');
  });

  test('WX-019 새로고침 버튼은 GET 재조회만', async ({ page }) => {
    const writes = writeGuard(page);
    await loginAsAdmin(page);
    await openWeatherValues(page);
    const before = await expectTableOrEmpty(page);
    const pending = waitForRequest(page, WEATHER_VALUES_RE);
    await page.getByTestId('admin-feature-weather-refresh').click();
    const res = await pending;
    expect(res.status()).toBe(200);
    const after = await expectTableOrEmpty(page);
    annotate(`rows before=${before} after=${after}`);
    expect(after === 0 ? before === 0 : before > 0, '재조회 전후 표 상태(빈/채움) 유지').toBeTruthy();
    expect(writes()).toEqual([]);
    await shot(page, 'WX-019', 'after-refresh');
  });
});
