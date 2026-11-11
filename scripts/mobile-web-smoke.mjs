// Expo Web 정적 산출물의 실제 CSS·입력·오류 표시를 N150 Chromium에서 확인한다.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
const origin = process.env.PINVI_MOBILE_SMOKE_URL ?? 'http://127.0.0.1:12805';
if (new URL(origin).hostname !== '127.0.0.1') throw new Error('격리 loopback 산출물만 검사하세요.');
const output = process.env.PINVI_MOBILE_SMOKE_OUTPUT ?? '/tmp/pinvi-mobile-smoke';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const viewport of [
    { width: 375, height: 812 },
    { width: 1280, height: 800 },
  ]) {
    const page = await browser.newPage({ viewport });
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('**/mobile/auth/**', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'AUTH_INVALID_CREDENTIALS', message: '테스트 인증 실패' },
        }),
      }),
    );
    await page.goto(origin + '/login/', { waitUntil: 'networkidle' });
    await page.getByPlaceholder('you@example.com').waitFor();
    await page.evaluate(() => document.fonts.ready);
    const style = await page
      .getByText('로그인', { exact: true })
      .first()
      .evaluate((el) => ({
        color: getComputedStyle(el).color,
        fontFamily: getComputedStyle(el).fontFamily,
        fontSize: getComputedStyle(el).fontSize,
      }));
    assert.equal(style.color, 'rgb(34, 34, 34)');
    assert.match(style.fontFamily, /Pretendard/);
    const email = page.getByPlaceholder('you@example.com');
    assert.equal(await email.evaluate((el) => getComputedStyle(el).borderRadius), '14px');
    await email.fill('not-an-email');
    await page.getByPlaceholder('비밀번호', { exact: true }).fill('short');
    await page.getByRole('button', { name: '로그인', exact: true }).click();
    assert.ok(
      await page.getByText(/올바른 이메일|이메일 형식|이메일 주소/).count(),
      '이메일 오류가 보여야 한다',
    );
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      true,
      '가로 overflow가 없어야 한다',
    );
    assert.deepEqual(errors, []);
    await page.screenshot({
      path: output + '/mobile-login-' + viewport.width + '.png',
      fullPage: true,
    });
    results.push({ viewport, style, validation: true, pageErrors: errors });
    await page.close();
  }
  writeFileSync(output + '/results.json', JSON.stringify(results, null, 2) + '\n');
  console.log('Expo Web 모바일·데스크톱 CSS/글꼴/입력/오류 스모크 PASS');
} finally {
  await browser.close();
}
