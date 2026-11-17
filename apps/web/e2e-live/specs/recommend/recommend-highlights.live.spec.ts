/**
 * REC — 추천 여행(/notice-plans) 카드의 '주변 축제·큐레이션' 펼침 + '내 여행에 추가'.
 * 화면: components/notice-plans/{NoticePlanShelf,NoticePlanHighlights,AddPlaceToTripDialog}.tsx
 * API: GET /notice-plans/{id}/highlights (Map /v1/curations + /v1/public/festivals/monthly).
 * pending deploy — 이 PR 이 prod 에 배포되기 전에는 토글이 없어 실패한다(catalog/recommend.yaml).
 */
import { expect, test, type Locator, type Page, type Response } from '@playwright/test';
import {
  createTrip,
  deleteTrip,
  e2ePrefix,
  isMobileProject,
  isoDate,
  loginAsUser,
  tripDayPoiCounts,
} from '../../helpers/live';

const isHighlights = (r: Response) =>
  r.request().method() === 'GET' && /\/notice-plans\/[0-9a-f-]{36}\/highlights$/.test(new URL(r.url()).pathname);

async function openShelf(page: Page): Promise<Locator[]> {
  await page.goto('/notice-plans');
  await expect(page.getByRole('heading', { name: '추천 여행', exact: true })).toBeVisible({ timeout: 20_000 });
  const list = page.getByTestId('notice-plan-list');
  await expect(list).toBeVisible({ timeout: 20_000 });
  return list.locator('[data-testid^="notice-plan-highlights-toggle-"]').all();
}

async function expand(page: Page, toggle: Locator): Promise<{ planId: string; body: Record<string, unknown> }> {
  const testId = (await toggle.getAttribute('data-testid')) ?? '';
  const planId = testId.replace('notice-plan-highlights-toggle-', '');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  const responded = page.waitForResponse(isHighlights, { timeout: 30_000 });
  await toggle.click();
  const res = await responded;
  expect(res.status()).toBe(200);
  const body = ((await res.json()) as { data: Record<string, unknown> }).data;
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByTestId(`notice-plan-highlights-${planId}`)).toBeVisible({ timeout: 20_000 });
  return { planId, body };
}

/** 구역은 목록·빈 문구·불가 안내 중 정확히 하나로 그려진다. */
async function sectionState(section: Locator): Promise<'items' | 'empty' | 'unavailable'> {
  if (await section.getByText('지금은 불러올 수 없습니다', { exact: false }).count()) return 'unavailable';
  if (await section.getByRole('listitem').count()) return 'items';
  await expect(section.getByText(/없습니다\.$/)).toBeVisible();
  return 'empty';
}

test.describe('REC 추천 여행 주변 축제·큐레이션', () => {
  let tripId: string | null = null;
  test.afterEach(async ({ page }) => {
    if (tripId) await deleteTrip(page, tripId).catch(() => undefined);
    tripId = null;
  });

  test('REC-001 카드 펼침 — 축제·큐레이션 두 구역', async ({ page }, testInfo) => {
    await loginAsUser(page);
    const toggles = await openShelf(page);
    test.skip(toggles.length === 0, '공개 추천 여행 없음(데이터 전제)');
    const toggle = toggles[0]!;
    const { planId, body } = await expand(page, toggle);
    expect(['plan', 'upcoming']).toContain(body.window_basis);
    expect(['sido', 'nationwide']).toContain(body.region_scope);

    const panel = page.getByTestId(`notice-plan-highlights-${planId}`);
    const events = await sectionState(panel.getByTestId('notice-plan-events'));
    const curated = await sectionState(panel.getByTestId('notice-plan-curated'));
    testInfo.annotations.push({
      type: 'highlights',
      description: `events=${events} curated=${curated} unavailable=${JSON.stringify(body.unavailable)}`,
    });
    // 2026-11-17: 축제는 plan 장소 bbox(±0.3°) 안에서만 고른다 — 가장 먼 행사 거리를 남긴다(게이트 아님:
    // 여러 장소에 걸친 plan은 bbox 안이어도 모든 장소에서 멀 수 있다).
    const distances = ((body.events as Array<{ distance_m: number | null }> | undefined) ?? [])
      .map((e) => e.distance_m)
      .filter((d): d is number => d != null);
    testInfo.annotations.push({
      type: 'events-max-distance-m',
      description: distances.length ? String(Math.max(...distances)) : 'n/a',
    });

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(panel).toHaveCount(0);
  });

  test('REC-002 주변 항목을 새 여행 1일차에 추가', async ({ page }, testInfo) => {
    test.skip(isMobileProject(), 'desktop only');
    await loginAsUser(page);
    const title = `${e2ePrefix} REC-002 ${Date.now()}`;
    tripId = (await createTrip(page, { title, start: isoDate(30), end: isoDate(31) })).id;
    expect(await tripDayPoiCounts(page, tripId)).toEqual([0, 0]);

    const toggles = await openShelf(page);
    let addButton: Locator | null = null;
    for (const toggle of toggles.slice(0, 5)) {
      const { planId } = await expand(page, toggle);
      const panel = page.getByTestId(`notice-plan-highlights-${planId}`);
      const candidate = panel.getByRole('button', { name: / 내 여행에 추가$/ }).first();
      if (await candidate.count()) {
        addButton = candidate;
        break;
      }
    }
    if (addButton == null) {
      testInfo.annotations.push({ type: 'skip-reason', description: '좌표 있는 주변 항목 없음' });
      test.skip(true, '좌표 있는 주변 항목 없음(데이터 전제)');
      return;
    }
    await addButton.click();
    const dialog = page.getByTestId('add-place-dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: title }).click();
    const day1 = dialog.getByRole('button', { name: /^1일차/ });
    await day1.click();
    await expect(day1).toHaveAttribute('aria-pressed', 'true');

    const created = page.waitForResponse(
      (r) => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(`/trips/${tripId}/pois`),
      { timeout: 30_000 },
    );
    await dialog.getByTestId('add-place-confirm').click();
    expect((await created).status()).toBe(201);
    await expect(dialog.getByRole('status')).toContainText('1일차');
    await expect(dialog.getByRole('link', { name: '여행 열기' })).toHaveAttribute('href', `/trips/${tripId}`);
    expect(await tripDayPoiCounts(page, tripId)).toEqual([1, 0]);
  });

  test('REC-003 모바일 — 가로 스크롤 없음 + 더 보기', async ({ page }, testInfo) => {
    test.skip(!isMobileProject(), 'mobile only');
    await loginAsUser(page);
    const toggles = await openShelf(page);
    test.skip(toggles.length === 0, '공개 추천 여행 없음(데이터 전제)');
    const { planId } = await expand(page, toggles[0]!);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);

    const panel = page.getByTestId(`notice-plan-highlights-${planId}`);
    const more = panel.getByRole('button', { name: /곳 더 보기$/ }).first();
    if (!(await more.count())) {
      testInfo.annotations.push({ type: 'more', description: "'더 보기' 없음(구역 항목 ≤ 3)" });
      return;
    }
    const section = more.locator('xpath=ancestor::section[1]');
    const before = await section.getByRole('listitem').count();
    await more.click();
    await expect(section.getByRole('button', { name: '접기' })).toHaveAttribute('aria-expanded', 'true');
    expect(await section.getByRole('listitem').count()).toBeGreaterThan(before);
  });
});
