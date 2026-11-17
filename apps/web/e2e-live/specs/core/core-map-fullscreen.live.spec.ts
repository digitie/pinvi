/**
 * CORE — 전체 화면 탐색 지도 + 여행 지도와 같은 장소 마커(소유자 요청 2026-11-17
 * "탐색지도의 마커도 여행과 동일하게. 지도도 전체화면으로.").
 *
 *  - CORE-048 탐색 지도 장소 마커 = 여행 지도 마커(원 + 상자 없는 이름 라벨, components/map/ExploreFeatureMarker.tsx)
 *  - CORE-049 /map 지도 canvas가 창을 덮는다(데스크톱: 얇은 상단 바 아래 전부, 모바일: 맨 위~하단 탭바), 가로 스크롤 없음,
 *             오버레이(검색·레이어 스택 / 확대·축소 / 내 위치)끼리 겹치지 않는다(components/app/AppShell.tsx `/map` 분기)
 *  - CORE-050 검색으로 고른 장소 popup이 레이어 체크박스를 덮지 않는다 — popup을 닫지 않고 바로 체크(lib/popupClearance.ts)
 *             2026-11-17 mobile NEAR-005의 원인(popup이 날씨 줄만큼 자라 '주유소' 체크박스를 덮었다)을 제품에서 고쳤다.
 *
 * 읽기 전용(장소 선택·레이어 토글은 화면 상태만 바꾼다). 토글은 끝에 되돌린다.
 */
import { expect, test, type Locator, type Page } from '@playwright/test';
import {
  clickableFeatureMarkers,
  ensureFeatureMarkers,
  loginAsUser,
  shot,
  waitForMapIdle,
} from '../../helpers/live';
import {
  exploreMarkers,
  intersects,
  isMobileViewport,
  waitForMapCanvas,
  type Box,
} from '../../helpers/core';
import { chip, controls, searchAndFly, waitForControls } from '../../helpers/nearby';

const box = async (locator: Locator): Promise<Box> => {
  const b = await locator.boundingBox();
  expect(b, 'element has a box').not.toBeNull();
  return b as Box;
};

/** `locator`의 가운데에서 맨 위 요소가 자기 자신(또는 그 label 안)인가 — 무엇에도 덮이지 않았다. */
async function isTopmost(locator: Locator): Promise<boolean> {
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!top && (top === el || el.contains(top) || !!el.closest('label')?.contains(top));
  });
}

async function viewport(page: Page): Promise<{ width: number; height: number }> {
  return page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
}

test.describe('CORE full-screen explore map', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsUser(page);
  });

  test('CORE-048 탐색 지도 장소 마커는 여행 지도와 같은 원 + 상자 없는 이름 라벨이다', async ({ page }) => {
    await page.goto('/map');
    await waitForMapCanvas(page);
    await ensureFeatureMarkers(page, 1);
    const [pin] = await clickableFeatureMarkers(page, 1);
    expect(pin, 'a clickable feature marker').toBeTruthy();
    // 같은 마커가 탐색 지도 class를 갖는다(= ExploreFeatureMarker → CirclePlaceMarker).
    await expect(pin!).toHaveClass(/\bexplore-map-marker\b/);
    expect(await exploreMarkers(page).count()).toBeGreaterThan(0);
    const name = ((await pin!.getAttribute('aria-label')) ?? '').trim();
    expect(name, 'marker aria-label = place name').not.toBe('');

    const dot = pin!.getByTestId('circle-place-marker-dot');
    const dotBox = await box(dot);
    // 여행 지도 장소 마커와 같은 22px 원(테두리 포함 반올림 오차 ±1).
    expect(Math.abs(Math.round(dotBox.width) - 22)).toBeLessThanOrEqual(1);
    expect(Math.abs(Math.round(dotBox.height) - 22)).toBeLessThanOrEqual(1);
    expect(await dot.evaluate((el) => getComputedStyle(el).borderRadius)).not.toBe('0px');
    // 원 안에 아이콘이 있다(카테고리 아이콘).
    await expect(dot.locator('[data-maki-icon]')).toHaveCount(1);

    const label = pin!.getByTestId('circle-place-marker-label');
    await expect(label).toBeVisible();
    await expect(label).toContainText(name.slice(0, 4));
    const style = await label.evaluate((el) => {
      const s = getComputedStyle(el);
      return { bg: s.backgroundColor, shadow: s.boxShadow, border: s.borderTopWidth };
    });
    expect(style, '상자 없는 글자 라벨').toEqual({ bg: 'rgba(0, 0, 0, 0)', shadow: 'none', border: '0px' });
    expect((await box(label)).x).toBeGreaterThan(dotBox.x + dotBox.width - 1);
    // 탐색 지도는 장소별 날씨를 받지 않는다 — 마커 날씨 아이콘 없음(새 API 호출 없음).
    await expect(pin!.getByTestId('place-weather-glyph')).toHaveCount(0);

    const featureId = ((await pin!.getAttribute('data-interaction-id')) ?? '').replace(/^feature:/, '');
    const legend = page.locator(`[data-testid="feature-map-marker-style"][data-feature-id="${featureId}"]`);
    await expect(legend).toHaveAttribute('data-marker-size', '22');
    await expect(legend).toHaveAttribute('data-marker-label', 'true');
    await shot(page, 'CORE-048', 'markers');

    // 누르면 오늘과 같은 상세 — 데스크톱은 popup, 모바일은 상세 시트만(CORE-045).
    await dot.click();
    if (isMobileViewport(page)) {
      await expect(page.getByTestId('feature-detail-modal')).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('.maplibregl-popup')).toHaveCount(0);
    } else {
      await expect(page.getByTestId('feature-map-popup')).toBeVisible({ timeout: 15_000 });
      await expect(legend).toHaveAttribute('data-marker-selected', 'true');
    }
  });

  test('CORE-049 /map 지도 canvas가 창을 덮고 오버레이끼리 겹치지 않는다(가로 스크롤 없음)', async ({ page }) => {
    await page.goto('/map');
    await waitForMapCanvas(page);
    await waitForControls(page);
    const vp = await viewport(page);
    const canvas = await box(page.locator('.maplibregl-canvas').first());

    expect(Math.round(canvas.x)).toBe(0);
    expect(Math.abs(canvas.width - vp.width)).toBeLessThanOrEqual(1);
    if (isMobileViewport(page)) {
      // 모바일: 상단 바 없음, 지도는 맨 위부터 하단 탭바 위까지.
      await expect(page.getByRole('banner')).toBeHidden();
      const tabbar = await box(page.locator('nav[aria-label="주요 메뉴"]'));
      expect(Math.round(canvas.y)).toBe(0);
      expect(Math.abs(canvas.y + canvas.height - tabbar.y)).toBeLessThanOrEqual(2);
    } else {
      // 데스크톱: 얇은 상단 바(전역 메뉴) 바로 아래부터 창 끝까지.
      const header = await box(page.getByRole('banner'));
      expect(header.height).toBeLessThanOrEqual(56);
      expect(Math.abs(canvas.y - (header.y + header.height))).toBeLessThanOrEqual(1);
      expect(Math.abs(canvas.y + canvas.height - vp.height)).toBeLessThanOrEqual(1);
    }
    const scroll = await page.evaluate(() => ({
      w: document.scrollingElement!.scrollWidth,
      h: document.scrollingElement!.scrollHeight,
    }));
    expect(scroll.w, '가로 스크롤 없음').toBeLessThanOrEqual(vp.width);
    expect(scroll.h, '페이지 세로 스크롤 없음').toBeLessThanOrEqual(vp.height);

    // 오버레이: 왼쪽 위 스택(검색·레이어) / 오른쪽 위 확대·축소 / 오른쪽 아래 내 위치 — 서로 겹치지 않고 지도 안.
    const stack = await box(page.getByTestId('feature-map-overlay-stack'));
    const myLocation = await box(page.getByTestId('map-my-location'));
    const zoom = page.locator('.maplibregl-ctrl-top-right .maplibregl-ctrl-group').first();
    expect(intersects(stack, myLocation)).toBe(false);
    if ((await zoom.count()) > 0) expect(intersects(stack, await box(zoom))).toBe(false);
    // 내 위치 버튼은 축척 막대·출처 표기 위에 있다(겹치지 않는다).
    for (const selector of ['.maplibregl-ctrl-scale', '.maplibregl-ctrl-attrib']) {
      const ctrl = page.locator(selector).first();
      if ((await ctrl.count()) > 0 && (await ctrl.isVisible())) {
        expect(intersects(myLocation, await box(ctrl)), `내 위치 버튼 vs ${selector}`).toBe(false);
      }
    }
    for (const b of [stack, myLocation]) {
      expect(b.x).toBeGreaterThanOrEqual(canvas.x);
      expect(b.x + b.width).toBeLessThanOrEqual(canvas.x + canvas.width);
      expect(b.y + b.height).toBeLessThanOrEqual(canvas.y + canvas.height);
    }
    expect(await isTopmost(page.getByTestId('map-my-location')), '내 위치 버튼이 눌린다').toBe(true);
    expect(await isTopmost(chip(page, 'fuel_station')), '주유소 체크박스가 눌린다').toBe(true);
    await shot(page, 'CORE-049', 'fullscreen');
  });

  test('CORE-050 검색으로 고른 장소 popup이 레이어 체크박스를 덮지 않는다(popup을 닫지 않고 체크)', async ({ page }) => {
    await page.goto('/map');
    await waitForMapCanvas(page);
    await waitForControls(page);
    // NEAR-005가 실패한 그 순서: '서울역' 검색 선택(zoom 15) → popup이 상세·날씨 줄만큼 자란다.
    await searchAndFly(page, '서울역');
    const popup = page.locator('.maplibregl-popup');
    await expect(popup).toBeVisible({ timeout: 15_000 });
    await waitForMapIdle(page);
    // 날씨 줄(최대 ~4 s)이 붙어 popup이 다 자란 뒤에도 패널과 겹치지 않아야 한다 — 지도가 비켜 선다.
    await expect
      .poll(async () => intersects(await box(popup), await box(controls(page))), { timeout: 10_000 })
      .toBe(false);
    const fuel = chip(page, 'fuel_station');
    expect(await isTopmost(fuel), 'popup이 주유소 체크박스를 덮지 않는다').toBe(true);
    const wasChecked = await fuel.isChecked();
    // popup을 닫지 않고 그대로 누른다(force 없이 — 덮였으면 'intercepts pointer events'로 실패한다).
    await fuel.setChecked(!wasChecked);
    await expect(fuel).toBeChecked({ checked: !wasChecked });
    await expect(popup).toBeVisible();
    await shot(page, 'CORE-050', 'popup-and-layers');
    await fuel.setChecked(wasChecked);
  });
});
