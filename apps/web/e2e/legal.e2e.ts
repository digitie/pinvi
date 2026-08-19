import { expect, test } from '@playwright/test';

/**
 * 법무 표면(Long Document) — T-316. 이 표면에는 e2e가 0건이었다.
 * measure 65ch·본문 16px·중립 초안 배너·공개 chrome(문서 간 이동)을 회귀로 고정한다.
 */

test('법무 문서가 Long Document 규격으로 렌더되고 공개 chrome을 쓴다', async ({ page }) => {
  await page.goto('/legal/terms-of-service');

  const doc = page.getByTestId('legal-doc');
  await expect(doc).toBeVisible();

  // measure: 65ch 프로브와 비교(문서에 박힌 값). 여유 2px.
  const { docWidth, probe, bodyFontSize } = await page.evaluate(() => {
    const article = document.querySelector('[data-testid="legal-doc"]') as HTMLElement;
    const paragraph = article.querySelector('section p') as HTMLElement;
    const probeEl = document.createElement('div');
    probeEl.style.width = '65ch';
    probeEl.style.position = 'absolute';
    probeEl.style.visibility = 'hidden';
    article.appendChild(probeEl);
    const probeWidth = probeEl.getBoundingClientRect().width;
    probeEl.remove();
    return {
      docWidth: article.getBoundingClientRect().width,
      probe: probeWidth,
      bodyFontSize: getComputedStyle(paragraph).fontSize,
    };
  });
  expect(docWidth).toBeLessThanOrEqual(probe + 2);
  // 본문은 보조 텍스트가 아니라 주 콘텐츠다.
  expect(bodyFontSize).toBe('16px');

  // 초안 배너는 error 팔레트를 쓰지 않는다(진짜 오류 신호를 죽이지 않게).
  const banner = page.getByTestId('legal-draft-banner');
  await expect(banner).toBeVisible();
  const bannerBg = await banner.evaluate((el) => getComputedStyle(el).backgroundColor);
  expect(bannerBg).not.toBe('rgb(253, 236, 234)');

  // 공개 chrome — 워드마크 + colophon의 법무 링크로 문서 간 이동이 된다.
  await expect(page.getByRole('link', { name: 'Pinvi 홈' })).toBeVisible();
  await page.getByRole('link', { name: '개인정보 처리방침' }).click();
  await expect(page).toHaveURL(/\/legal\/privacy-policy$/);
  await expect(page.getByTestId('legal-doc')).toBeVisible();

  // 4번째 문서도 colophon에서 도달할 수 있다(수기 목록이라 빠져 있었다).
  await expect(page.getByRole('link', { name: '개인위치정보 수집·이용' })).toBeVisible();
});
