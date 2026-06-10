import { expect, test } from '@playwright/test';

const isFetch = (resourceType: string) => ['fetch', 'xhr'].includes(resourceType);

test('여행 생성 폼: 제목 없이 제출하면 제목 필드 오류 + aria-invalid', async ({ page }) => {
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.goto('/trips');
  await expect(page.getByRole('heading', { name: '여행' })).toBeVisible();

  // 제목 비운 채 제출.
  await page.getByTestId('trip-create-submit').click();

  const titleError = page.locator('#trip-create-title-error');
  await expect(titleError).toBeVisible();
  await expect(titleError).toHaveText(/제목/);
  await expect(page.getByTestId('trip-create-title')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('trip-create-title')).toBeFocused();
});

test('여행 생성 폼: label↔input 연결(제목 클릭 시 포커스)', async ({ page }) => {
  await page.route(/.*\/trips(\?.*)?$/, async (route, request) => {
    if (!isFetch(request.resourceType())) return route.continue();
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: [] }) });
  });

  await page.goto('/trips');
  await page.getByText('제목', { exact: true }).click();
  await expect(page.getByTestId('trip-create-title')).toBeFocused();
});

test('프로필 완성 폼: 필수 동의 후 닉네임 없이 제출하면 닉네임 오류', async ({ page }) => {
  await page.goto('/profile-complete');
  await expect(page.getByRole('heading', { name: '프로필 완성하기' })).toBeVisible();

  // 필수 동의 4종 체크(닉네임 검증까지 진행되도록).
  for (const type of ['tos', 'privacy', 'lbs_tos', 'location_collection']) {
    await page.getByTestId(`consent-required-${type}`).check();
  }

  await page.getByTestId('profile-submit').click();

  const nickError = page.locator('#profile-nickname-error');
  await expect(nickError).toBeVisible();
  await expect(page.getByTestId('profile-nickname')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByTestId('profile-nickname')).toBeFocused();
});
