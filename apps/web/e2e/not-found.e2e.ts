import { expect, test } from '@playwright/test';

test('알 수 없는 경로는 not-found 페이지를 보여준다', async ({ page }) => {
  const res = await page.goto('/this-route-does-not-exist-9z9z');
  expect(res?.status()).toBe(404);

  const panel = page.getByTestId('not-found-page');
  await expect(panel).toBeVisible();
  await expect(panel.getByRole('heading', { name: '페이지를 찾을 수 없습니다' })).toBeVisible();
});

test('not-found 페이지의 홈 링크로 이동한다', async ({ page }) => {
  await page.goto('/nope-nope-nope');
  await page.getByTestId('not-found-page').getByRole('link', { name: '홈으로' }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: 'TripMate', exact: true })).toBeVisible();
});
