/**
 * SRCH-019..034 — one case per Map category family + Kakao/Naver fallback. Read-only on prod.
 * Category labels: kor-travel-map src/kortravelmap/category/_definitions.py leaf names, surfaced by PinVi
 * as `category_label` (apps/api/app/services/category_labels.py) and rendered in
 * FeatureDetailCardBody `-category` (apps/web/components/map/FeatureDetailCardBody.tsx).
 */
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  CATEGORY_CODE_RE,
  desktopOnly,
  featureRows,
  gotoExplore,
  modal,
  runSearch,
  searchPickOpenDetail,
  searchRows,
} from '../../helpers/search';

/** Open the first feature row's detail; if the family has no feature rows, accept external rows and return null. */
async function familyCase(
  page: Page,
  testInfo: TestInfo,
  id: string,
  q: string,
  labelRe: RegExp,
  pickName?: RegExp,
) {
  const probe = await runSearch(page, q);
  const feats = featureRows(probe.rows).filter((r) => (pickName ? pickName.test(r.name) : true) && r.coord != null);
  if (feats.length === 0) {
    const external = probe.rows.filter((r) => r.source === 'kakao' || r.source === 'naver');
    testInfo.annotations.push({ type: 'data', description: `${id}: no Map feature for '${q}', external rows=${external.length}` });
    expect(external.length + probe.rows.length, 'some result').toBeGreaterThan(0);
    return null;
  }
  const { card, picked } = await searchPickOpenDetail(page, q, (r) => r === feats[0] || (r.source === 'feature' && r.name === feats[0]!.name));
  expect(picked.source).toBe('feature');
  const category = modal.field(page, 'category');
  if (await category.count()) {
    const label = (await category.innerText()).trim();
    expect(label).not.toMatch(CATEGORY_CODE_RE);
    expect.soft(label, `${id} category label for ${card.name}`).toMatch(labelRe);
  } else {
    expect.soft(card.category_label ?? null, `${id} category_label present`).not.toBeNull();
  }
  await shot(page, id, 'detail');
  return card;
}

test.describe('SRCH sources by category family (/map)', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await gotoExplore(page);
  });

  test('SRCH-019 숙박·호텔', async ({ page }, ti) => {
    desktopOnly();
    test.fail(true, 'kor-travel-map#1438: feature category misclassified (숙박·카페·마트·캠핑장·주차장 → 관광/문화시설)');
    await familyCase(page, ti, 'SRCH-019', '롯데호텔', /호텔|숙박|리조트/);
  });

  test('SRCH-020 숙박·캠핑장', async ({ page }, ti) => {
    desktopOnly();
    test.fail(true, 'kor-travel-map#1438: feature category misclassified (숙박·카페·마트·캠핑장·주차장 → 관광/문화시설)');
    await familyCase(page, ti, 'SRCH-020', '오토캠핑장', /캠핑|글램핑|카라반/);
  });

  test('SRCH-021 음식점', async ({ page }, ti) => {
    desktopOnly();
    await familyCase(page, ti, 'SRCH-021', '안동찜닭', /한식|음식점|식음|분식/);
  });

  test('SRCH-022 카페', async ({ page }, ti) => {
    desktopOnly();
    test.fail(true, 'kor-travel-map#1438: feature category misclassified (숙박·카페·마트·캠핑장·주차장 → 관광/문화시설)');
    await familyCase(page, ti, 'SRCH-022', '카페', /카페|커피|디저트|베이커리/);
  });

  // SRCH-023 (등산로 route kind) and SRCH-028 (국립공원 area kind) are `blocked`: PinVi in-bounds renders
  // only place/event/notice/price kinds, so there is no UI to assert on. See catalog notes.

  test('SRCH-025 국가유산 소수서원', async ({ page }, ti) => {
    desktopOnly();
    // /map biases toward the current (Seoul) viewport (#615, order-only): rows inside the bbox come
    // first, so the exact match need not be row 1 — it must be present and open as a heritage card.
    const probe = await runSearch(page, '소수서원');
    expect(featureRows(probe.rows).map((r) => r.name)).toContainEqual(expect.stringContaining('소수서원'));
    await familyCase(page, ti, 'SRCH-025', '소수서원', /국가유산|사적|기념물|전통사찰|관광|한옥/, /소수서원$/);
  });

  test('SRCH-027 축제/행사 kind=event', async ({ page }, ti) => {
    desktopOnly();
    test.fail(true, 'kor-travel-map#1439: event features have no period/venue');
    const card = await familyCase(page, ti, 'SRCH-027', '축제', /축제|행사|관광|공원|문화/);
    if (!card) return;
    const kind = await modal.body(page).getAttribute('data-kind');
    expect(['event', 'place']).toContain(kind);
    if (kind === 'event') {
      const period = modal.field(page, 'period');
      const venue = modal.field(page, 'venue');
      expect.soft((await period.count()) + (await venue.count()), 'event shows period or venue').toBeGreaterThan(0);
    } else {
      ti.annotations.push({ type: 'data', description: 'first 축제 hit is a place, not an event feature' });
    }
  });

  test('SRCH-031 박물관/미술관', async ({ page }, ti) => {
    desktopOnly();
    await familyCase(page, ti, 'SRCH-031', '국립중앙박물관', /박물관|문화시설|미술관/);
  });

  test('SRCH-033 공항', async ({ page }, ti) => {
    desktopOnly();
    // Map search has no airport feature for 김포공항 (airports come from the transport layer, NEAR-*);
    // only airport-named rows count — tenants like '롯데마트 김포공항점' are not airports.
    const card = await familyCase(page, ti, 'SRCH-033', '김포공항', /공항|교통/, /공항$/);
    test.skip(card == null, 'data absent: Map 검색에 공항 feature 없음(교통 레이어가 담당)');
  });

  test('SRCH-034 카카오/네이버 fallback + back-link', async ({ page }, ti) => {
    const out = await runSearch(page, '스타벅스 안동옥동점');
    const internalPlaces = out.rows.filter((r) => r.source === 'feature' || r.source === 'my_poi').length;
    const external = out.rows.filter((r) => r.source === 'kakao' || r.source === 'naver');
    ti.annotations.push({ type: 'data', description: `internal=${internalPlaces} external=${external.length} degraded=${out.degraded.join(',')}` });
    if (internalPlaces >= 5) {
      // short-circuit: providers not called by contract (docs/api/search.md)
      expect(external.length).toBe(0);
      return;
    }
    for (const src of ['kakao', 'naver'] as const) {
      const rows = out.rows.filter((r) => r.source === src);
      if (out.degraded.includes(src)) {
        expect(rows.length, `${src} degraded ⇒ no rows`).toBe(0);
        continue;
      }
      if (rows.length === 0) continue;
      const first = searchRows(page, src).first();
      await expect(first).toContainText(src === 'kakao' ? '카카오' : '네이버 검색');
      const withLink = rows.find((r) => r.provider_url);
      if (withLink) {
        const link = page.getByTestId(`map-search-backlink-${src}`).first();
        await expect(link).toHaveAttribute('target', '_blank');
        await expect(link).toHaveAttribute('rel', /noopener/);
        await expect(link).toHaveAttribute('aria-label', src === 'kakao' ? '카카오에서 열기' : '네이버 검색에서 열기');
        await expect(link).toHaveAttribute('href', /^https?:\/\//);
      }
    }
    expect.soft(external.length, 'at least one external row when internal < K').toBeGreaterThan(0);
    await shot(page, 'SRCH-034', 'external-rows');
  });
});
