/**
 * SRCH-055 — performance sweep (record + soft-assert). Budgets from the brief: 2-char search < 8s,
 * detail card < 3s. The 2026-11-02 prod e2e measured 16s before #614 (geo 504 ×3 retries); #614 made the
 * sources concurrent with a 3s address budget, so a breach now points at Map or geo, not PinVi.
 */
import { expect, test } from '@playwright/test';
import { loginAsUser } from '../../helpers/live';
import { desktopOnly, featureRows, gotoExplore, recordPerf, runSearch, searchPickOpenDetail } from '../../helpers/search';

test.describe('SRCH perf', () => {
  desktopOnly();

  test('SRCH-055 2글자 검색 스윕 + 상세 카드', async ({ page }, ti) => {
    await loginAsUser(page);
    await gotoExplore(page);
    let lastWithFeature: string | null = null;
    for (const q of ['설악', '부산', '제주']) {
      const out = await runSearch(page, q);
      recordPerf(ti, `search('${q}')`, out.elapsedMs, 8_000);
      ti.annotations.push({ type: 'data', description: `${q}: rows=${out.rows.length} degraded=${out.degraded.join(',') || '-'}` });
      expect(out.status).toBe(200);
      if (featureRows(out.rows).some((r) => r.coord)) lastWithFeature = q;
    }
    expect(lastWithFeature, 'at least one query returned a feature row').not.toBeNull();
    const { elapsedMs, card } = await searchPickOpenDetail(page, lastWithFeature!, (r) => r.source === 'feature' && r.coord != null);
    recordPerf(ti, `detail-card(${card.name})`, elapsedMs, 3_000);
  });
});
