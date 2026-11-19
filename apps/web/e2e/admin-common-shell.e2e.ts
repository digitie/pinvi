import { test, expect } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { join } from 'node:path';

// 공통 관리자 셸(@kor-travel/ui 0.2.3 AdminShell). lg(1024) 이상은 좌측 rail, 그 아래는 상단 바의
// 메뉴 버튼으로 여는 좌측 drawer다. drawer가 열린 동안 메뉴가 DOM에 두 벌이고 메뉴 버튼은 Radix
// aria-hidden 뒤에 있어 data-slot과 dialog 범위로 찾는다.
const RAIL = '[data-slot="admin-shell-rail"]';
const MENU_BUTTON = '[data-slot="admin-shell-menu-button"]';
const HEADER = '[data-slot="admin-shell-header"]';
const TITLE = '[data-slot="admin-shell-title"]';
const DESCRIPTION = '[data-slot="admin-shell-description"]';

const user = {
  user_id: '77777777-7777-4777-8777-777777777777',
  email: 'admin@example.com',
  nickname: '관리자',
  avatar_url: null,
  status: 'active',
  roles: ['user', 'admin'],
  email_verified_at: '2026-06-01T09:00:00+09:00',
  has_password: true,
  oauth_identities: [],
};

async function mockAdmin(page: Page) {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: user }) }),
  );
  for (const path of ['/admin/trips', '/admin/users'])
    await page.route(
      (url) => url.port === '12801' && url.pathname === path,
      (route) =>
        route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ data: { items: [], total: 0, page: 1, limit: 50 } }),
        }),
    );
}

const output = process.env.PINVI_PLAYWRIGHT_RUNNER_OUTPUT_DIR;

test('공통 Admin 셸: rail 메뉴·PinVi 색상·접힘 저장·로그아웃(데스크톱)', async ({ page }) => {
  await mockAdmin(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/admin/trips');
  const rail = page.locator(RAIL);
  const nav = rail.getByRole('navigation', { name: '관리자 주요 메뉴' });
  await expect(nav.getByRole('link')).toHaveCount(30);
  await expect(nav.locator('[aria-current="page"]')).toHaveAttribute('href', '/admin/trips');
  await expect(rail).toHaveCSS('width', '256px');
  await expect(page.locator(MENU_BUTTON)).toBeHidden();
  expect(
    await nav.evaluate((el) => {
      const style = getComputedStyle(el);
      return (
        style.getPropertyValue('--kt-brand-tint').trim() ===
        style.getPropertyValue('--color-admin-brand-tint').trim()
      );
    }),
  ).toBe(true);
  await nav.getByRole('link', { name: '사용자', exact: true }).focus();
  await expect(nav.getByRole('link', { name: '사용자', exact: true })).toBeFocused();
  const scan = await new AxeBuilder({ page })
    .include(RAIL)
    .include(HEADER)
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(scan.violations).toEqual([]);
  const links = nav.getByRole('link');
  await links.nth(28).focus();
  await page.keyboard.press('Tab');
  await expect(links.last()).toBeFocused();
  await expect(links.last()).toBeInViewport();
  await page.getByRole('link', { name: '본문으로 건너뛰기' }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-desktop.png'), fullPage: true });
  await page.getByRole('button', { name: 'Admin 메뉴 접기' }).click();
  await expect(rail).toHaveCSS('width', '64px');
  await expect(rail).toHaveAttribute('data-collapsed', 'true');
  await page.reload();
  await expect(page.locator(RAIL)).toHaveAttribute('data-collapsed', 'true');
  // 접힌 rail에서도 메뉴의 접근성 이름은 라벨이다.
  await expect(nav.getByRole('link', { name: '여행', exact: true })).toBeVisible();
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-collapsed.png'), fullPage: true });
  await page.getByRole('button', { name: 'Admin 메뉴 펼치기' }).click();
  await expect(rail).toHaveCSS('width', '256px');
  let logoutAttempts = 0;
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/logout',
    async (route) => {
      logoutAttempts += 1;
      await route.fulfill(
        logoutAttempts === 1
          ? {
              status: 500,
              contentType: 'application/json',
              body: JSON.stringify({
                error: { code: 'INTERNAL_ERROR', message: '검증용 내부 오류' },
              }),
            }
          : { status: 204 },
      );
    },
  );
  await rail.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(rail.getByRole('alert')).toContainText('로그아웃하지 못했습니다.');
  await expect(page).toHaveURL(/\/admin\/trips/);
  await rail.getByRole('button', { name: '로그아웃', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/login/);
  await expect(page.getByTestId('admin-login-form')).toBeVisible();
  if (output)
    await page.screenshot({ path: join(output, 'pinvi-admin-login.png'), fullPage: true });
});

test('공통 Admin 셸: 모바일 메뉴는 좌측 drawer로 접힌다', async ({ page }) => {
  await mockAdmin(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin/trips');
  await expect(page.locator(TITLE)).toHaveText('Pinvi 운영 - 여행');
  await expect(page.locator(RAIL)).toBeHidden();
  const menuButton = page.locator(MENU_BUTTON);
  await expect(menuButton).toBeVisible();
  await expect(menuButton).toHaveAccessibleName('Admin 메뉴 열기');
  await expect(menuButton).toHaveCSS('min-height', '44px');
  if (output) await page.screenshot({ path: join(output, 'pinvi-admin-mobile.png') });

  await menuButton.click();
  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();
  await expect(drawer).toHaveAttribute('data-slot', 'admin-shell-drawer');
  // 좌측에서 열리고 최대 280px.
  await expect.poll(async () => (await drawer.boundingBox())?.x).toBe(0);
  expect((await drawer.boundingBox())?.width ?? 0).toBeLessThanOrEqual(280);
  const nav = drawer.getByRole('navigation', { name: '관리자 주요 메뉴' });
  await expect(nav.getByRole('link')).toHaveCount(30);
  await expect(nav.locator('[aria-current="page"]')).toHaveAttribute('href', '/admin/trips');
  // drawer는 Portal이라 `[data-pv-surface='admin']` 밖이지만 같은 PinVi 토큰을 받는다.
  expect(
    await drawer.evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        mapped:
          style.getPropertyValue('--kt-brand-tint').trim() ===
          style.getPropertyValue('--color-admin-brand-tint').trim(),
        textSm: style.getPropertyValue('--text-sm').trim(),
      };
    }),
  ).toEqual({ mapped: true, textSm: '0.9375rem' });
  await expect(nav.getByRole('link', { name: '사용자', exact: true })).toHaveCSS(
    'min-height',
    '44px',
  );
  await expect(drawer.getByRole('button', { name: '로그아웃', exact: true })).toHaveCSS(
    'min-height',
    '44px',
  );
  await expect(drawer.getByTestId('admin-me')).toHaveAttribute(
    'aria-label',
    '로그인 사용자 admin@example.com',
  );
  if (output) await page.screenshot({ path: join(output, 'pinvi-admin-mobile-drawer.png') });

  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
  await expect(menuButton).toBeFocused();

  // drawer 안 메뉴로 이동하면 drawer가 닫힌 채 새 페이지가 뜬다.
  await menuButton.click();
  await page.getByRole('dialog').getByRole('link', { name: '사용자', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.locator(TITLE)).toHaveText('Pinvi 운영 - 사용자');
  await expect(page.getByRole('dialog')).toHaveCount(0);

  for (const width of [320, 375, 414, 768, 1023]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(MENU_BUTTON)).toBeVisible();
    await expect(page.locator(RAIL)).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  // lg로 넓어지면 열린 drawer가 닫히고 rail이 돌아온다.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(MENU_BUTTON).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator(RAIL)).toBeVisible();
});

test('공통 Admin 셸: 맨 위 한 줄은 "영역 - 페이지" 제목과 작은 설명뿐이다(PC·모바일)', async ({
  page,
}) => {
  await mockAdmin(page);
  for (const { width, height } of [
    { width: 1280, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width, height });
    for (const route of [
      { path: '/admin/users', title: 'Pinvi 운영 - 사용자', description: '운영 계정 조회와 상태 관리' },
      { path: '/admin/trips', title: 'Pinvi 운영 - 여행', description: '여행계획 조회와 운영 상태 관리' },
    ]) {
      await page.goto(route.path);
      const header = page.locator(HEADER);
      const title = page.locator(TITLE);
      await expect(title).toHaveText(route.title);
      // h1은 상단 바의 그것 하나뿐이고 <main> 밖이다. 본문에 따로 제목·앱 설명을 두지 않는다.
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1 })).toHaveAccessibleName(route.title);
      await expect(page.getByRole('main').getByRole('heading', { level: 1 })).toHaveCount(0);
      // 페이지 설명은 상단 바에 작게(12px) 한 줄로 둔다.
      const description = header.locator(DESCRIPTION);
      await expect(description).toHaveText(route.description);
      await expect(description).toHaveCSS('font-size', '12px');
      await expect(description).toHaveCSS('white-space', 'nowrap');
      await expect(page.getByRole('main')).not.toContainText(route.description);
      // 상단 바는 한 줄(약 48px)이다.
      const box = await header.boundingBox();
      expect(box?.height ?? 0).toBeLessThanOrEqual(56);
      const titleBox = await title.boundingBox();
      const descriptionBox = await description.boundingBox();
      if (width >= 1024 || (descriptionBox?.width ?? 0) > 0)
        expect(
          Math.abs((titleBox?.y ?? 0) + (titleBox?.height ?? 0) - ((descriptionBox?.y ?? 0) + (descriptionBox?.height ?? 0))),
        ).toBeLessThanOrEqual(6);
      if (output)
        await page.screenshot({
          path: join(output, `pinvi-admin-title-${width}-${route.path.replace(/\W+/g, '-')}.png`),
        });
    }
  }
});
