/**
 * SRCH-035..039 — feature detail card (modal). Read-only on prod.
 * UI source: apps/web/components/map/FeatureDetailModal.tsx (Dialog testids: feature-detail-modal,
 * -title, -close, -body, -loading, -error), FeatureDetailCardBody.tsx (feature-detail-card-body-*),
 * FeatureDetailModalController.tsx (subtitle = category_label · address_line).
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot } from '../../helpers/live';
import {
  CATEGORY_CODE_RE,
  KNOWN_CATEGORY_LABELS,
  desktopOnly,
  featureRows,
  gotoExplore,
  mobileOnly,
  modal,
  recordPerf,
  runSearch,
  searchPickOpenDetail,
} from '../../helpers/search';

test.describe('SRCH detail card', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
    await gotoExplore(page);
  });

  test('SRCH-035 핵심 필드 + 라벨 + 주소 + 3초', async ({ page }, ti) => {
    const { card, elapsedMs } = await searchPickOpenDetail(page, '안동하회마을');
    recordPerf(ti, 'detail-card(안동하회마을)', elapsedMs, 3_000);
    await expect(modal.title(page)).toContainText(card.name);
    await expect(modal.body(page)).toHaveAttribute('data-kind', 'place');

    const category = modal.field(page, 'category');
    expect(await category.count(), 'category label row rendered').toBeGreaterThan(0);
    const label = (await category.innerText()).trim();
    expect(label).not.toMatch(CATEGORY_CODE_RE);
    expect.soft(KNOWN_CATEGORY_LABELS.has(label), `label '${label}' is a Map catalog leaf name`).toBe(true);

    const address = modal.field(page, 'address');
    await expect(address).toBeVisible();
    await expect(address).toContainText(/경상북도|경북|안동/);
    expect(card.address_line).toBeTruthy();

    // subtitle = 'category · address'
    const dialog = modal.root(page);
    await expect(dialog).toContainText(`${label} · `);
    await shot(page, 'SRCH-035', 'detail');
  });

  test('SRCH-036 전화/영업시간/홈페이지는 값이 있을 때만', async ({ page }, ti) => {
    desktopOnly();
    const probe = await runSearch(page, '국립중앙박물관');
    const q = featureRows(probe.rows).length > 0 ? '국립중앙박물관' : '안동하회마을';
    const { card } = await searchPickOpenDetail(page, q);
    ti.annotations.push({
      type: 'data',
      description: `${card.name}: phone=${card.phone ?? '-'} hours=${card.business_hours ?? '-'} homepage=${card.homepage_url ?? '-'}`,
    });
    await expect(modal.field(page, 'phone')).toHaveCount(card.phone ? 1 : 0);
    await expect(modal.field(page, 'hours')).toHaveCount(card.business_hours ? 1 : 0);
    await expect(modal.field(page, 'homepage')).toHaveCount(card.homepage_url ? 1 : 0);
    if (card.phone) await expect(modal.field(page, 'phone')).toContainText(card.phone);
    if (card.business_hours) await expect(modal.field(page, 'hours')).toContainText(card.business_hours);
    if (card.homepage_url) {
      const link = modal.field(page, 'homepage').getByRole('link', { name: '홈페이지' });
      await expect(link).toHaveAttribute('href', /^https?:\/\//);
      await expect(link).toHaveAttribute('target', '_blank');
    }
    await shot(page, 'SRCH-036', 'detail-fields');
  });

  test('SRCH-037 카카오·네이버에서 더 보기', async ({ page }, ti) => {
    desktopOnly();
    await searchPickOpenDetail(page, '안동하회마을');
    const button = modal.field(page, 'load-enrichment');
    await expect(button).toHaveText('카카오·네이버에서 더 보기');
    const enriched = page.waitForResponse(
      (res) => /\/features\/[^/]+\/detail-card$/.test(new URL(res.url()).pathname) && new URL(res.url()).searchParams.has('providers'),
      { timeout: 30_000 },
    );
    await button.click();
    const res = await enriched;
    expect(new URL(res.url()).searchParams.get('providers')).toMatch(/kakao/);
    const json = (await res.json()) as { data: { enrichment: Array<{ provider: string; matched: boolean; provider_url: string | null }>; degraded_providers: string[] } };
    await expect(page.getByText('외부 정보 불러오는 중…')).toBeHidden({ timeout: 30_000 });
    ti.annotations.push({ type: 'data', description: `enrichment=${JSON.stringify(json.data.enrichment.map((e) => [e.provider, e.matched]))} degraded=${json.data.degraded_providers.join(',')}` });
    for (const row of json.data.enrichment) {
      const li = page.getByTestId(`feature-detail-enrichment-${row.provider}`);
      await expect(li).toBeVisible();
      await expect(li).toContainText(row.provider === 'kakao' ? '카카오' : '네이버 검색');
      await expect(li).toHaveAttribute('data-matched', row.matched ? 'true' : 'false');
      if (!row.matched) await expect(li).toContainText('일치하는 외부 정보 없음');
      if (row.provider_url) {
        const link = page.getByTestId(`feature-detail-enrichment-${row.provider}-link`);
        await expect(link).toHaveText(/지도에서 보기/);
        await expect(link).toHaveAttribute('target', '_blank');
      }
    }
    await expect(modal.field(page, 'enrichment-degraded')).toHaveCount(json.data.degraded_providers.length > 0 ? 1 : 0);
    await shot(page, 'SRCH-037', 'enrichment');
  });

  test('SRCH-038 모달 닫기 — × 와 Escape', async ({ page }) => {
    await searchPickOpenDetail(page, '안동하회마을');
    await modal.close(page).click();
    await expect(modal.root(page)).toBeHidden();
    // reopen via the still-selected popup
    await page.getByTestId('feature-map-detail-open').click();
    await expect(modal.body(page)).toBeVisible({ timeout: 15_000 });
    await page.keyboard.press('Escape');
    await expect(modal.root(page)).toBeHidden();
  });

  test('SRCH-039 모바일 bottom-sheet', async ({ page }) => {
    mobileOnly();
    await searchPickOpenDetail(page, '안동하회마을');
    const viewport = page.viewportSize()!;
    const box = await modal.root(page).boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeLessThanOrEqual(viewport.width + 1);
    expect.soft(box!.y + box!.height, 'sheet bottom within viewport').toBeLessThanOrEqual(viewport.height + 1);
    expect.soft(box!.y + box!.height, 'sheet sits at the bottom edge').toBeGreaterThan(viewport.height * 0.9);
    await expect(modal.body(page)).toBeVisible();
    await shot(page, 'SRCH-039', 'mobile-sheet');
  });
});
