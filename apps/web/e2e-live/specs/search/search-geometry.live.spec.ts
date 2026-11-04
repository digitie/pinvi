/** #635: 실제 적재된 도형과 근처 point fixture를 사용한다. 제품 HTTP를 mock하지 않는다. */
import { expect, test, type Page } from '@playwright/test';
import { FeatureSummarySchema } from '@pinvi/schemas';
import { loginAsUser } from '../../helpers/live';
import { desktopOnly, gotoExplore, searchPickOpenDetail } from '../../helpers/search';

async function showGeometry(page: Page, kind: 'route' | 'area', anchor: string) {
  await gotoExplore(page);
  // coord가 없는 도형을 가짜 point로 바꾸지 않는다. 별도 근처 point로 이동한다.
  await searchPickOpenDetail(page, anchor, (row) => row.coord != null);
  await page.keyboard.press('Escape');
  const response = page.waitForResponse((res) => {
    const url = new URL(res.url());
    return (
      url.pathname.endsWith('/features/in-bounds') &&
      url.searchParams.get('include_geometry') === 'true' &&
      url.searchParams.get('kinds') === kind
    );
  });
  await page.getByTestId('geometry-' + kind + '-toggle').check();
  const res = await response;
  expect(res.status()).toBe(200);
  expect(Number(new URL(res.url()).searchParams.get('zoom'))).toBeGreaterThanOrEqual(14);
  const body = (await res.json()) as { data: { items: unknown[] } };
  return body.data.items.map((item) => FeatureSummarySchema.parse(item));
}

test.describe('경로·영역 실제 geometry', () => {
  test('SRCH-023 대청봉 경로 토글·목록 선택·상세', async ({ page }) => {
    desktopOnly();
    const anchor = process.env.PINVI_E2E_GEOMETRY_SEORAK_ANCHOR_QUERY ?? '';
    test.skip(!anchor, '설악산 경로와 교차하는 근처 point 검색 fixture를 명시해야 한다');
    await loginAsUser(page);
    const rows = await showGeometry(page, 'route', anchor);
    const route = rows.find((row) => row.kind === 'route' && row.name.includes('대청봉'));
    expect(route, '근처 point의 지도 범위에 대청봉 route fixture가 있어야 한다').toBeDefined();
    expect(['LineString', 'MultiLineString']).toContain(route!.geometry?.type);
    await page.getByText(/경로·영역 목록/).click();
    const item = page.getByTestId('geometry-list-item').filter({ hasText: route!.name });
    await expect(item).toHaveAttribute('data-feature-id', route!.feature_id);
    await item.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('geometry-popup')).toContainText(route!.name);
    await page.getByTestId('geometry-detail-open').click();
    await expect(page.getByRole('dialog')).toContainText(route!.name);
  });

  test('SRCH-024 북한산 경로 복수 part·목록·OFF', async ({ page }) => {
    desktopOnly();
    const anchor = process.env.PINVI_E2E_GEOMETRY_BUKHAN_ANCHOR_QUERY ?? '';
    test.skip(!anchor, '북한산 경로들과 교차하는 근처 point 검색 fixture를 명시해야 한다');
    await loginAsUser(page);
    const rows = await showGeometry(page, 'route', anchor);
    const routes = rows.filter((row) => row.kind === 'route' && row.name.includes('북한산'));
    expect(routes.length).toBeGreaterThanOrEqual(2);
    for (const route of routes)
      expect(['LineString', 'MultiLineString']).toContain(route.geometry?.type);
    await expect(page.getByTestId('geometry-list-item')).toHaveCount(rows.length);
    await page.getByTestId('geometry-route-toggle').uncheck();
    await expect(page.getByTestId('geometry-list-item')).toHaveCount(0);
    await expect(page.getByTestId('geometry-popup')).toHaveCount(0);
  });

  test('SRCH-028 국립공원 영역·큰 bounds 선택 후 상세 유지', async ({ page }) => {
    desktopOnly();
    const anchor = process.env.PINVI_E2E_GEOMETRY_SEORAK_ANCHOR_QUERY ?? '';
    test.skip(!anchor, '설악산 영역과 교차하는 근처 point 검색 fixture를 명시해야 한다');
    await loginAsUser(page);
    const rows = await showGeometry(page, 'area', anchor);
    const area = rows.find((row) => row.kind === 'area' && row.name.includes('설악산'));
    expect(area, '근처 point의 지도 범위에 설악산 area fixture가 있어야 한다').toBeDefined();
    expect(['Polygon', 'MultiPolygon']).toContain(area!.geometry?.type);
    await page.getByText(/경로·영역 목록/).click();
    await page.getByTestId('geometry-list-item').filter({ hasText: area!.name }).click();
    await expect(page.getByTestId('geometry-popup')).toContainText(area!.name);
    await page.getByTestId('geometry-detail-open').click();
    await expect(page.getByRole('dialog')).toContainText(area!.name);
  });
});
