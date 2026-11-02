/**
 * SRCH-001..012 — basic place search on the explore map (/map). Read-only on prod.
 * UI source: apps/web/components/map/MapSearchBox.tsx (badges, alert texts, testids),
 *            apps/web/components/map/FeatureMapView.tsx (popup '상세보기' = feature-map-detail-open).
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  CATEGORY_CODE_RE,
  SOURCE_BADGE,
  desktopOnly,
  featureRows,
  gotoExplore,
  recordPerf,
  runSearch,
  searchAlert,
  searchInput,
  searchRows,
} from '../../helpers/search';

test.describe('SRCH basic search (/map)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await gotoExplore(page);
  });

  test('SRCH-001 2글자 검색 → 8초 내 결과 + 소스 배지', async ({ page }, testInfo) => {
    const out = await runSearch(page, '설악');
    recordPerf(testInfo, "search('설악')", out.elapsedMs, 8_000);
    expect(out.status).toBe(200);
    expect(out.rows.length, 'at least one result').toBeGreaterThan(0);
    expect(new URL(out.requestUrl).searchParams.get('limit')).toBe('8');
    const rows = searchRows(page);
    await expect(rows.first()).toBeVisible();
    const n = await rows.count();
    for (let i = 0; i < n; i += 1) {
      const text = (await rows.nth(i).innerText()).replace(/\s+/g, ' ');
      const badge = Object.values(SOURCE_BADGE).find((b) => text.includes(b));
      expect(badge, `row ${i} has a source badge: ${text}`).toBeTruthy();
    }
    await shot(page, 'SRCH-001', 'results');
  });

  test('SRCH-002 정확한 이름 → 장소 행 첫 번째, 둘째 줄은 라벨', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '안동하회마을');
    const first = out.rows[0];
    expect(first?.source, 'first row source').toBe('feature');
    expect(first?.name).toContain('하회마을');
    const firstRow = searchRows(page).first();
    await expect(firstRow).toContainText('장소');
    const secondary = (first?.road_address ?? first?.address ?? first?.category_label ?? null) as string | null;
    if (secondary) {
      await expect(firstRow).toContainText(secondary);
      expect(secondary, 'secondary line is a label, not a code').not.toMatch(CATEGORY_CODE_RE);
    }
    await shot(page, 'SRCH-002', 'results');
  });

  test('SRCH-003 1글자는 검색하지 않는다', async ({ page }) => {
    desktopOnly();
    let searchCalls = 0;
    page.on('request', (req) => {
      if (req.method() === 'GET' && new URL(req.url()).pathname.endsWith('/search')) searchCalls += 1;
    });
    await searchInput(page).fill('설');
    await page.waitForTimeout(1_000);
    expect(searchCalls).toBe(0);
    await expect(searchRows(page)).toHaveCount(0);
    await expect(searchAlert(page)).toHaveCount(0);
  });

  test('SRCH-004 전체 주소 질의 → 주소 배지', async ({ page }, testInfo) => {
    desktopOnly();
    const out = await runSearch(page, '경북 안동시 풍천면 하회종가길 40');
    if (out.degraded.includes('addresses')) {
      testInfo.annotations.push({ type: 'degraded', description: 'geo addresses degraded in this run' });
      expect.soft(out.degraded, 'addresses source degraded').not.toContain('addresses');
      return;
    }
    const addr = out.rows.filter((r) => r.source === 'address');
    expect(addr.length, 'address rows').toBeGreaterThan(0);
    await expect(searchRows(page, 'address').first()).toContainText('주소');
    await expect(searchRows(page, 'address').first()).toContainText(addr[0]!.name);
    await shot(page, 'SRCH-004', 'address-rows');
  });

  test('SRCH-005 도로명 부분 주소', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '하회종가길');
    expect(out.rows.length).toBeGreaterThan(0);
    expect.soft(out.rows.some((r) => r.source === 'address'), 'has an address row').toBe(true);
  });

  test('SRCH-006 부분 질의 하회마 → trigram 매칭', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '하회마');
    expect(featureRows(out.rows).some((r) => r.name.replace(/\s/g, '').includes('하회마을'))).toBe(true);
  });

  test('SRCH-007 무의미 질의 → 검색 결과가 없습니다', async ({ page }) => {
    const out = await runSearch(page, 'zzqqxxw');
    expect(out.rows.length).toBe(0);
    await expect(searchAlert(page)).toHaveText('검색 결과가 없습니다.');
    await expect(searchRows(page)).toHaveCount(0);
    await shot(page, 'SRCH-007', 'empty');
  });

  test('SRCH-008 공백 trim', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '  고씨굴  ');
    expect(new URL(out.requestUrl).searchParams.get('q')).toBe('고씨굴');
    expect(out.rows.length).toBeGreaterThan(0);
  });

  test('SRCH-009 Enter 즉시 검색, 페이지 이동 없음', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '소수서원', { submitWithEnter: true });
    expect(out.status).toBe(200);
    expect(out.rows.length).toBeGreaterThan(0);
    await expect(page).toHaveURL(/\/map(?:[?#].*)?$/);
  });

  test('SRCH-010 121자 질의 → alert, 크래시 없음', async ({ page }) => {
    desktopOnly();
    const long = 'ㄱ'.repeat(121);
    const out = await runSearch(page, long);
    expect([200, 422]).toContain(out.status);
    await expect(searchAlert(page)).toBeVisible();
    await expect(page.getByRole('heading', { name: '탐색 지도' })).toBeVisible();
  });

  test('SRCH-011 소스별 상한, 더 보기 없음', async ({ page }) => {
    desktopOnly();
    const out = await runSearch(page, '카페');
    const count = (s: string) => out.rows.filter((r) => r.source === s).length;
    expect(count('feature')).toBeLessThanOrEqual(8);
    expect(count('address')).toBeLessThanOrEqual(8);
    expect(count('my_poi')).toBeLessThanOrEqual(10);
    expect(count('kakao')).toBeLessThanOrEqual(8);
    expect(count('naver')).toBeLessThanOrEqual(5);
    await expect(page.getByRole('button', { name: /더 보기/ })).toHaveCount(0);
    expect(await searchRows(page).count()).toBe(out.rows.length);
  });

  test('SRCH-012 결과 선택 → 초기화 + 팝업 상세보기', async ({ page }) => {
    const out = await runSearch(page, '안동하회마을');
    const idx = out.rows.findIndex((r) => r.source === 'feature' && r.coord != null);
    expect(idx, 'a feature row with coord').toBeGreaterThanOrEqual(0);
    await searchRows(page).nth(idx).getByRole('button').first().click();
    await expect(searchInput(page)).toHaveValue('');
    await expect(searchRows(page)).toHaveCount(0);
    const detailOpen = page.getByTestId('feature-map-detail-open');
    await expect(detailOpen).toBeVisible({ timeout: 15_000 });
    await expect(detailOpen).toHaveText('상세보기');
    await expect(page.getByText(out.rows[idx]!.name).first()).toBeVisible();
    await shot(page, 'SRCH-012', 'popup');
  });
});
