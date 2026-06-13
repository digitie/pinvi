import { expect, test } from '@playwright/test';

test('지도 shell이 kor-travel-map feature 조회 없이 렌더링된다', async ({ page }) => {
  const requests: string[] = [];

  page.on('request', (request) => {
    requests.push(request.url());
  });

  await page.goto('/trips/map-shell');

  await expect(page.getByRole('heading', { name: '지도' })).toBeVisible();
  await expect(page.getByTestId('trip-map-shell')).toBeVisible();

  const fallback = page.getByTestId('vworld-map-fallback');
  const canvas = page.locator('.maplibregl-canvas').first();
  const renderedMapState = fallback.or(canvas);

  await expect(renderedMapState).toBeVisible();

  if (await fallback.isVisible()) {
    await expect(fallback).toContainText('VWorld API 키가 설정되지 않았습니다.');
  } else {
    await expect(canvas).toBeVisible();
  }

  expect(requests.some((url) => url.includes('/features/in-bounds'))).toBe(false);
  expect(requests.some((url) => url.includes('12701'))).toBe(false);
});
