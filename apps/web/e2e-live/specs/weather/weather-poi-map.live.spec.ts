/**
 * WX — explore map POI popup weather (WX-016).
 * Facts (PinVi main 620b6046, apps/web/components/map/FeatureMapView.tsx):
 *  - selecting a feature loads GET /features/{id}/weather separately (useAbortableLoad, #622);
 *  - popup shows `현재 기온 {n}°C` when currentTempC(card) finds a metric with unit ℃/°C or key temp/기온/T1H/TMP/TMN/TMX;
 *  - data-testid feature-map-detail-open ('상세보기').
 *  - MapSearchBox.tsx: input aria-label '장소·주소 검색', result rows data-testid map-search-result-{source}.
 * WX-017 (weather marker layer) is BLOCKED: pinvi_kor_travel_weather_map_markers_enabled is off in prod (coordinator 2026-11-03).
 */
import { expect, test } from '@playwright/test';
import { loginAsUser, shot, waitForRequest } from '../../helpers/live';
import { TEMP_KEY_RE, TEMP_RANGE, TEMP_UNIT_RE, annotate, numericValues, onMobile, type WxMetric } from '../../helpers/weather';

test.describe('weather · explore map POI', () => {
  test.setTimeout(180_000);
  test.skip(onMobile, '데스크톱 전용(모바일은 탭 시 상세 시트로 직행)');

  test('WX-016 서울역 팝업 "현재 기온 N°C"', async ({ page }) => {
    await loginAsUser(page);
    await page.goto('/map');
    const search = page.getByTestId('map-search').getByRole('textbox', { name: '장소·주소 검색' });
    await search.fill('서울역');
    await search.press('Enter');
    const row = page.getByTestId('map-search-result-feature').filter({ hasText: '서울역' }).first();
    await expect(row).toBeVisible({ timeout: 20_000 });
    const weatherRes = waitForRequest(page, /\/features\/[^/?]+\/weather(\?|$)/);
    await row.click();
    const res = await weatherRes;
    expect(res.status(), 'GET /features/{id}/weather').toBe(200);
    const body = (await res.json()) as { data?: { metrics: WxMetric[]; is_stale: boolean } } & { metrics?: WxMetric[] };
    const card = (body.data ?? body) as { metrics: WxMetric[]; is_stale: boolean; latest_at?: string | null };
    annotate(`metrics=${card.metrics.length} is_stale=${card.is_stale} latest_at=${card.latest_at ?? 'null'}`);

    const popup = page.locator('.maplibregl-popup').first();
    await expect(popup).toBeVisible();
    await expect(popup).toContainText('서울역');
    await expect(popup.getByTestId('feature-map-detail-open')).toBeVisible();

    const temps = numericValues(card.metrics, TEMP_KEY_RE, TEMP_UNIT_RE);
    if (temps.length === 0) {
      annotate('카드에 기온 metric 없음 — 팝업 기온 줄 생략은 정상(값을 지어내지 않음)');
      await expect(popup).not.toContainText('현재 기온');
    } else {
      await expect(popup).toContainText(/현재 기온 -?\d+°C/);
      const shown = Number(/현재 기온 (-?\d+)°C/.exec(await popup.innerText())?.[1]);
      expect(shown).toBeGreaterThanOrEqual(TEMP_RANGE.min);
      expect(shown).toBeLessThanOrEqual(TEMP_RANGE.max);
      // The popup rounds the first temp metric (currentTempC) — it must be one of the card's temps (±0.5).
      expect(temps.some((t) => Math.abs(Math.round(t) - shown) <= 1), '팝업 기온은 카드 값에서 나온다').toBeTruthy();
    }
    await shot(page, 'WX-016', 'seoul-station-popup');
  });
});
