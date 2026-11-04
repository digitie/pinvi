/**
 * SRCH-049..054 — Map #1436 ranking rules as observed through PinVi `/search`.
 * The /map viewport adds an order-only bbox bias (#615), so each test first zooms to national scale: when the
 * bias bbox covers Korea every row is "inside" and region_biased_items returns Map's order unchanged.
 * All ranking assertions are soft (prod data drift) except "row exists".
 */
import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  bboxSpansKorea,
  categoryRankWeight,
  desktopOnly,
  featureRows,
  gotoExplore,
  runSearch,
  searchPickOpenDetail,
  zoomToNation,
  type SearchOutcome,
} from '../../helpers/search';

const norm = (s: string) => s.replace(/\s+/g, '');

test.describe('SRCH ranking (Map #1436) on /map at national zoom', () => {
  desktopOnly();

  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await gotoExplore(page);
    await zoomToNation(page);
  });

  async function nationalSearch(page: Page, q: string, ti: TestInfo): Promise<SearchOutcome> {
    const out = await runSearch(page, q);
    ti.annotations.push({ type: 'bias', description: `bbox=${out.bbox ? out.bbox.join(',') : 'none'}` });
    expect.soft(bboxSpansKorea(out.bbox), 'viewport bias covers Korea (Map order preserved)').toBe(true);
    return out;
  }

  test("SRCH-049 '하회마을' → 안동하회마을 first", async ({ page }, ti) => {
    const out = await nationalSearch(page, '하회마을', ti);
    const feats = featureRows(out.rows);
    expect(feats.length).toBeGreaterThan(0);
    expect.soft(norm(feats[0]!.name), 'first feature row').toMatch(/^안동하회마을/);
    await shot(page, 'SRCH-049', 'results');
  });

  test("SRCH-050 alias '고씨동굴' → 영월 고씨굴 first", async ({ page }, ti) => {
    const out = await nationalSearch(page, '고씨동굴', ti);
    const feats = featureRows(out.rows);
    expect(feats.length, '고씨동굴 resolves to at least one feature').toBeGreaterThan(0);
    expect.soft(norm(feats[0]!.name)).toContain('고씨굴');
    const { card } = await searchPickOpenDetail(page, '고씨동굴', (r) => r.source === 'feature' && norm(r.name).includes('고씨굴'));
    expect.soft(card.address_line ?? '', 'address mentions 영월').toContain('영월');
    await shot(page, 'SRCH-050', 'detail');
  });

  test('SRCH-051 주차장은 명소 아래, 이름은 ○○ 주차장', async ({ page }, ti) => {
    for (const [q, attraction] of [
      ['하회마을', /하회마을/],
      ['도산서원', /도산서원/],
    ] as const) {
      const out = await nationalSearch(page, q, ti);
      const feats = featureRows(out.rows);
      const attractionIdx = feats.findIndex((r) => attraction.test(norm(r.name)) && !/주차장/.test(r.name));
      const parkingIdx = feats.findIndex((r) => /주차장/.test(r.name));
      ti.annotations.push({ type: 'data', description: `${q}: attraction@${attractionIdx} parking@${parkingIdx}` });
      if (parkingIdx >= 0) {
        expect.soft(attractionIdx, `${q}: attraction present`).toBeGreaterThanOrEqual(0);
        expect.soft(parkingIdx, `${q}: parking after the attraction`).toBeGreaterThan(attractionIdx);
        const parking = feats[parkingIdx]!;
        expect.soft(parking.name, "'○○ 주차장' naming").toMatch(/\S+\s주차장$/);
        if (parking.category_label) expect.soft(parking.category_label).toBe('주차장');
      }
    }
  });

  test('SRCH-052 관광 > 숙박 > 식음 > 기타 ordering', async ({ page }, ti) => {
    const out = await nationalSearch(page, '안동', ti);
    const weights = featureRows(out.rows)
      .map((r) => categoryRankWeight(r.category))
      .filter((w): w is number => w != null);
    ti.annotations.push({ type: 'data', description: `tier weights in order: ${weights.join(' ')}` });
    expect(weights.length).toBeGreaterThan(0);
    const sorted = [...weights].sort((a, b) => a - b);
    expect.soft(weights, 'tier-1 weights are non-decreasing').toEqual(sorted);
  });

  test('SRCH-053 병원은 마지막', async ({ page }, ti) => {
    for (const q of ['안동', '서울']) {
      const out = await nationalSearch(page, q, ti);
      const feats = featureRows(out.rows);
      const firstMedical = feats.findIndex((r) => (r.category ?? '').startsWith('07'));
      if (firstMedical < 0) {
        ti.annotations.push({ type: 'data', description: `${q}: no medical rows` });
        continue;
      }
      const after = feats.slice(firstMedical);
      expect.soft(after.every((r) => (r.category ?? '').startsWith('07')), `${q}: nothing non-medical after the first hospital`).toBe(true);
    }
  });

  test("SRCH-054 '서울역' exact first", async ({ page }, ti) => {
    const out = await nationalSearch(page, '서울역', ti);
    const feats = featureRows(out.rows);
    expect(feats.length).toBeGreaterThan(0);
    const first = norm(feats[0]!.name);
    expect.soft(first, 'exact station first').toMatch(/^서울역/);
    expect.soft(first).not.toContain('박물관');
    await shot(page, 'SRCH-054', 'results');
  });
});
