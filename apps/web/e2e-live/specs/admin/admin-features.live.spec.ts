// ADM-015..020 — Map feature admin proxy: search, 3-axis verification states, detail subpages (sources/overrides/weather-values);
// ADM-038 — change-requests page known drift.
// Selectors: admin/features/page.tsx, admin/features/[feature_id]/FeatureDetailSubpage.tsx, admin/features/change-requests/page.tsx
// Labels: lib/admin/status-label.ts (active 활성 · retired 종료 · published 공개 · suppressed 비공개 · valid 유효 · quarantined 격리)
import { expect, test } from '@playwright/test';
import { loginAsAdmin, shot, isMobileProject } from '../../helpers/live';
import { adminSelect, searchAdminFeatures, waitForGet } from '../../helpers/admin';

const PLACE = '안동하회마을'; // Map category family: heritage

test.describe.serial('ADM features', () => {
  let featureId = '';

  test.beforeEach(async ({ page }) => {
    test.skip(isMobileProject(), 'desktop only');
    await loginAsAdmin(page);
  });

  test('ADM-015 + ADM-016 search 안동하회마을, state badges and detail inspector', async ({ page }) => {
    await page.goto('/admin/features');
    await page.getByTestId('admin-features-search').fill(PLACE);
    await searchAdminFeatures(page); // #648 (fixed by #660): Korean q must answer < 500

    const row = page.locator('[data-testid^="admin-features-row-"]').filter({ hasText: PLACE }).first();
    await expect(row).toBeVisible({ timeout: 30_000 });
    const axes = row.getByTestId('admin-features-state-axes');
    await expect(axes).toContainText('활성');
    await expect(axes).toContainText('공개');
    await expect(axes).toContainText('유효');
    await expect(page.getByText(/\d+ms/)).toBeVisible();
    featureId = (await row.getAttribute('data-testid'))!.replace('admin-features-row-', '');
    expect(featureId).not.toBe('');
    await shot(page, 'ADM-015', 'list');

    // ADM-016
    const detail = waitForGet(page, new RegExp(`/admin/features/${featureId}$`));
    await row.getByTestId(`admin-features-detail-${featureId}`).click();
    await detail;
    const panel = page.getByTestId('admin-features-detail');
    await expect(panel).toContainText(PLACE);
    await expect(panel).toContainText('place');
    await expect(panel).toContainText(/-?\d+\.\d{5}, -?\d+\.\d{5}/);
    await expect(panel).toContainText(/sources \d+/);
    await expect(panel).toContainText(/curations \d+/);
    for (const tab of ['sources', 'overrides', 'weather-values']) {
      await expect(panel.getByTestId(`admin-features-link-${tab}`)).toHaveAttribute('href', `/admin/features/${encodeURIComponent(featureId)}/${tab}`);
    }
    await shot(page, 'ADM-016', 'detail');
  });

  test('ADM-017 state-axis filters are forwarded and rows match the axis', async ({ page }) => {
    await page.goto('/admin/features');
    const checks: Array<{ testid: string; value: string; param: string; label: string }> = [
      { testid: 'admin-features-lifecycle-filter', value: 'retired', param: 'lifecycle_state=retired', label: '종료' },
      { testid: 'admin-features-publication-filter', value: 'suppressed', param: 'publication_state=suppressed', label: '비공개' },
      { testid: 'admin-features-quality-filter', value: 'quarantined', param: 'quality_state=quarantined', label: '격리' },
    ];
    for (const c of checks) {
      const res = waitForGet(page, new RegExp(`/admin/features\\?.*${c.param}`), 60_000);
      await adminSelect(page, c.testid).selectOption(c.value);
      const response = await res;
      expect(new URL(response.url()).search).toContain(c.param);
      const rows = page.locator('[data-testid^="admin-features-row-"]');
      // the table re-renders after the response — wait for rows or the empty state before counting
      await expect(rows.first().or(page.getByText('feature가 없습니다.'))).toBeVisible({ timeout: 20_000 });
      const count = await rows.count();
      if (count === 0) {
        await expect(page.getByText('feature가 없습니다.')).toBeVisible();
      } else {
        for (let i = 0; i < Math.min(count, 25); i += 1) await expect(rows.nth(i).getByTestId('admin-features-state-axes')).toContainText(c.label);
      }
      // '전체' must drop the parameter entirely (page comment: new axis values must not be silently cut).
      // '전체' may be served from the query cache (same params as an earlier state) — when a request is
      // made it must not carry the axis parameter.
      const reset = waitForGet(page, /\/admin\/features\?/, 8_000).catch(() => null);
      await adminSelect(page, c.testid).selectOption('all');
      const resetRes = await reset;
      if (resetRes) expect(new URL(resetRes.url()).search).not.toContain(c.param.split('=')[0]);
      await expect(adminSelect(page, c.testid)).toHaveValue('all');
    }
  });

  test('ADM-018 + ADM-019 sources and overrides subpages', async ({ page }) => {
    test.skip(!featureId, 'needs ADM-015');
    await page.goto(`/admin/features/${encodeURIComponent(featureId)}/sources`);
    await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible();
    await expect(page.locator('[data-testid^="admin-feature-source-row-"]').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId('admin-feature-tab-overrides')).toHaveAttribute('href', `/admin/features/${featureId}/overrides`);
    await expect(page.getByTestId('admin-feature-tab-weather-values')).toHaveAttribute('href', `/admin/features/${featureId}/weather-values`);
    await shot(page, 'ADM-018', 'sources');

    await page.goto(`/admin/features/${encodeURIComponent(featureId)}/overrides`);
    await expect(page.getByTestId('admin-feature-subpage')).toBeVisible();
    await expect(page.getByTestId('admin-feature-tab-error')).toHaveCount(0);
  });

  test('ADM-020 weather-values subpage shows rows and the stale/fresh flag', async ({ page }) => {
    test.skip(!featureId, 'needs ADM-015');
    const weather = waitForGet(page, new RegExp(`/admin/features/${featureId}/weather-values`), 60_000);
    await page.goto(`/admin/features/${encodeURIComponent(featureId)}/weather-values`);
    const res = await weather;
    expect(res.status(), 'weather proxy must be up (503 = WEATHER_SERVICE_UNAVAILABLE is a real finding)').toBe(200);
    const section = page.locator('section', { hasText: 'weather values' }).first();
    await expect(section).toContainText('asof');
    await expect(section).toContainText('latest');
    await expect(section).toContainText(/\b(fresh|stale)\b/);
    const rows = page.locator('[data-testid^="admin-feature-weather-row-"]');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const ids = await rows.evaluateAll((els) => els.map((e) => e.getAttribute('data-testid')));
    expect(new Set(ids).size).toBe(ids.length);
    await expect(rows.first()).toContainText(/nowcast|short|medium|observation|warning/);
    const flag = (await section.textContent())?.includes('stale') ? 'stale' : 'fresh';
    test.info().annotations.push({ type: 'weather-flag', description: flag });
    await shot(page, 'ADM-020', 'weather-values');
  });

  test('ADM-038 change-requests page: record Map drift branch without crashing', async ({ page }) => {
    const res = waitForGet(page, /\/admin\/features\/change-requests/, 60_000);
    await page.goto('/admin/features/change-requests');
    const response = await res;
    await expect(page.getByRole('heading', { name: 'Feature 변경 요청' })).toBeVisible();
    const error = page.getByTestId('admin-fcr-error');
    const empty = page.getByTestId('admin-fcr-detail-empty');
    const rows = page.locator('[data-testid^="admin-fcr-select-"]');
    await expect(error.or(empty).or(rows.first())).toBeVisible({ timeout: 30_000 });
    if (await error.count()) {
      await expect(error).toContainText(/찾을 수 없습니다|사용 불가|올바르지 않습니다/);
      test.info().annotations.push({ type: 'drift', description: `upstream ${response.status()}: ${((await error.textContent()) ?? '').slice(0, 80)}` });
    } else {
      test.info().annotations.push({ type: 'drift', description: `list rendered (${await rows.count()} rows) — Map still serves change-requests` });
    }
    await expect(page.getByText(/Application error|Unhandled Runtime Error/)).toHaveCount(0);
    await shot(page, 'ADM-038', 'change-requests');
  });
});
