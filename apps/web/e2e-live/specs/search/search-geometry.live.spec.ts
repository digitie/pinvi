/** #635: 실제 적재된 도형과 근처 point fixture를 사용한다. 제품 HTTP를 mock하지 않는다. */
import { expect, test, type Page } from '@playwright/test';
import { FeatureSummarySchema } from '@pinvi/schemas';
import {
  clickRenderedGeometry,
  openGeometryDetail,
  expectGeometryRemoved,
  renderedMap,
  waitForCamera,
  waitForGeometry,
} from '../../helpers/geometry';
import { loginAsUser } from '../../helpers/live';
import { desktopOnly, gotoExplore, searchPickOpenDetail } from '../../helpers/search';

// 운영 Map 데이터로 확인한 근처 point(2026-11-05): 줌 15 화면 안에 '설악산_대청봉'·'북한산_백운대'
// route가 여럿 걸린다. 다른 환경은 env로 바꾼다.
const SEORAK_ANCHOR = '설악산국립공원';
const BUKHAN_ANCHOR = '북한산성';

async function showGeometry(page: Page, kind: 'route' | 'area', anchor: string) {
  await gotoExplore(page);
  // coord가 없는 도형을 가짜 point로 바꾸지 않는다. 별도 근처 point로 이동한다.
  // 같은 이름의 경로 행(중심 좌표가 있다)이 아니라 이름이 정확히 같은 point feature로 이동한다.
  await searchPickOpenDetail(
    page,
    anchor,
    (row) => row.source === 'feature' && row.coord != null && row.name === anchor,
  );
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
    const anchor = process.env.PINVI_E2E_GEOMETRY_SEORAK_ANCHOR_QUERY || SEORAK_ANCHOR;
    await loginAsUser(page);
    const rows = await showGeometry(page, 'route', anchor);
    const route = rows.find((row) => row.kind === 'route' && row.name.includes('대청봉'));
    expect(route, '근처 point의 지도 범위에 대청봉 route fixture가 있어야 한다').toBeDefined();
    expect(['LineString', 'MultiLineString']).toContain(route!.geometry?.type);
    const map = await renderedMap(page);
    await clickRenderedGeometry(page, map, route!.feature_id);
    await page
      .getByTestId('geometry-popup')
      .getByRole('button', { name: '경로·영역 닫기' })
      .click();
    await page.getByText(/경로·영역 목록/).click();
    const item = page.getByTestId('geometry-list-item').filter({ hasText: route!.name });
    await expect(item).toHaveAttribute('data-feature-id', route!.feature_id);
    await item.focus();
    await page.keyboard.press('Enter');
    await waitForCamera(map);
    await expect(page.getByTestId('geometry-popup')).toHaveAttribute(
      'data-feature-id',
      route!.feature_id,
    );
    await expect(page.getByTestId('geometry-popup')).toContainText(route!.name);
    await openGeometryDetail(page, route!.feature_id, 'route');
  });

  test('SRCH-024 북한산 경로 복수 part·목록·OFF', async ({ page }) => {
    desktopOnly();
    const anchor = process.env.PINVI_E2E_GEOMETRY_BUKHAN_ANCHOR_QUERY || BUKHAN_ANCHOR;
    await loginAsUser(page);
    const rows = await showGeometry(page, 'route', anchor);
    const routes = rows.filter((row) => row.kind === 'route' && row.name.includes('북한산'));
    expect(routes.length).toBeGreaterThanOrEqual(2);
    for (const route of routes)
      expect(['LineString', 'MultiLineString']).toContain(route.geometry?.type);
    const map = await renderedMap(page);
    for (const route of routes) await waitForGeometry(map, route.feature_id);
    await clickRenderedGeometry(page, map, routes[0]!.feature_id);
    await page.getByText(/경로·영역 목록/).click();
    await expect(page.getByTestId('geometry-list-item').first()).toBeVisible();
    await expect(page.getByTestId('geometry-list-item')).toHaveCount(rows.length);
    await page.getByTestId('geometry-route-toggle').uncheck();
    await expectGeometryRemoved(
      map,
      rows.map((row) => row.feature_id),
    );
    await expect(page.getByTestId('geometry-list-item')).toHaveCount(0);
    await expect(page.getByTestId('geometry-popup')).toHaveCount(0);
  });

  test('SRCH-028 국립공원 영역·큰 bounds 선택 후 상세 유지', async ({ page }) => {
    desktopOnly();
    const anchor = process.env.PINVI_E2E_GEOMETRY_AREA_ANCHOR_QUERY ?? '';
    // 운영 Map에 area kind가 아직 0건이다(2026-11-05 전국 in-bounds kind=area 0) — 적재 뒤 env로 켠다.
    test.skip(
      !anchor,
      '설악산 영역과 교차하는 근처 point 검색 fixture(PINVI_E2E_GEOMETRY_AREA_ANCHOR_QUERY)가 필요하다',
    );
    await loginAsUser(page);
    const rows = await showGeometry(page, 'area', anchor);
    const area = rows.find((row) => row.kind === 'area' && row.name.includes('설악산'));
    expect(area, '근처 point의 지도 범위에 설악산 area fixture가 있어야 한다').toBeDefined();
    expect(['Polygon', 'MultiPolygon']).toContain(area!.geometry?.type);
    const map = await renderedMap(page);
    await clickRenderedGeometry(page, map, area!.feature_id);
    await page
      .getByTestId('geometry-popup')
      .getByRole('button', { name: '경로·영역 닫기' })
      .click();
    const naturalZoom = await map.evaluate((m, geometry) => {
      const positions: number[][] = [];
      const visit = (value: unknown): void => {
        if (!Array.isArray(value)) return;
        if (typeof value[0] === 'number' && typeof value[1] === 'number') {
          positions.push(value as number[]);
          return;
        }
        value.forEach(visit);
      };
      visit(geometry!.coordinates);
      const lngs = positions.map((p) => p[0]!),
        lats = positions.map((p) => p[1]!);
      return m.cameraForBounds(
        [
          [Math.min(...lngs), Math.min(...lats)],
          [Math.max(...lngs), Math.max(...lats)],
        ],
        { padding: 48, maxZoom: 16 },
      )?.zoom;
    }, area!.geometry);
    expect(naturalZoom, '전체 영역 fit이 14 미만인 큰 fixture여야 한다').toBeLessThan(14);
    await page.getByText(/경로·영역 목록/).click();
    await page.getByTestId('geometry-list-item').filter({ hasText: area!.name }).click();
    await waitForCamera(map);
    expect(await map.evaluate((m) => m.getZoom())).toBeGreaterThanOrEqual(14);
    await expect(page.getByTestId('geometry-popup')).toHaveAttribute(
      'data-feature-id',
      area!.feature_id,
    );
    await expect(page.getByTestId('geometry-popup')).toContainText(area!.name);
    await openGeometryDetail(page, area!.feature_id, 'area');
  });
});
