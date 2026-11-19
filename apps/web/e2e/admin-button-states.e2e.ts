import { test, expect } from './fixtures';
import type { Page } from '@playwright/test';
import { buttonVariants } from '@kor-travel/ui/button-variants';
import { join } from 'node:path';

// FS-7.8 버튼 테두리 점검. 관리자 범위의 버튼 변형마다 Tab 포커스·hover·active·disabled를 잰다.
// - Tab 포커스: outline 2px 단일(solid, offset 2px), box-shadow ring 없음, 테두리 두께 불변
// - hover·active(누르는 중): 테두리 두께 불변, 포커스 outline 없음, 위치 이동 1px 이하
// - disabled: 테두리 두께가 활성 상태와 같다
// 공통 Button(cva)은 실제 `buttonVariants`로, 손으로 만든 페이지 버튼은 페이지에 있는 클래스 그대로
// 관리자 `<main>` 안에 심는다(관리자 CSS 범위·토큰을 그대로 받는다). 셸 자신의 버튼도 함께 잰다.

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

const VARIANTS = [
  'default',
  'outline',
  'secondary',
  'ghost',
  'destructive',
  'destructive-solid',
  'link',
] as const;

// 페이지에서 그대로 옮긴 손 버튼(abuse/backup 새로고침, trips 생성, etl 갱신).
const LEGACY = {
  'legacy-refresh':
    'inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft',
  'legacy-cta':
    'inline-flex items-center gap-2 rounded-sm bg-cta hover:bg-cta-hover px-3 py-2 text-sm text-on-primary',
  'legacy-small':
    'inline-flex items-center gap-1 rounded-sm border border-hairline px-3 py-1 text-sm',
} as const;

type Probe = {
  bw: string;
  outlineStyle: string;
  outlineWidth: string;
  outlineOffset: string;
  boxShadow: string;
  focusVisible: boolean;
  x: number;
  y: number;
};

async function probe(page: Page, selector: string): Promise<Probe> {
  return page.locator(selector).evaluate((el) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      bw: [s.borderTopWidth, s.borderRightWidth, s.borderBottomWidth, s.borderLeftWidth].join(' '),
      outlineStyle: s.outlineStyle,
      outlineWidth: s.outlineWidth,
      outlineOffset: s.outlineOffset,
      boxShadow: s.boxShadow,
      focusVisible: el.matches(':focus-visible'),
      x: r.x,
      y: r.y,
    };
  });
}

async function mountFixture(page: Page) {
  const fixtures = [
    ...VARIANTS.map((variant) => ({
      id: `btn-${variant}`,
      className: buttonVariants({ variant }),
      label: variant,
    })),
    ...Object.entries(LEGACY).map(([id, className]) => ({ id, className, label: id })),
  ];
  await page.getByRole('main').evaluate((main, items) => {
    const box = document.createElement('div');
    box.id = 'button-state-fixture';
    box.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;padding:12px;';
    const start = document.createElement('span');
    start.id = 'fixture-start';
    start.tabIndex = -1;
    start.textContent = '시작';
    box.append(start);
    for (const item of items) {
      for (const disabled of [false, true]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.id = disabled ? `${item.id}-disabled` : item.id;
        button.className = item.className;
        button.textContent = disabled ? `${item.label} (disabled)` : item.label;
        button.disabled = disabled;
        box.append(button);
      }
    }
    main.prepend(box);
  }, fixtures);
  return fixtures.map((item) => item.id);
}

async function setup(page: Page) {
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/auth/me',
    (route) =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify({ data: user }) }),
  );
  await page.route(
    (url) => url.port === '12801' && url.pathname === '/admin/users',
    (route) =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { items: [], total: 0, page: 1, limit: 50 } }),
      }),
  );
  await page.goto('/admin/users');
  await expect(page.locator('[data-slot="admin-shell-title"]')).toHaveText('Pinvi 운영 - 사용자');
}

const output = process.env.PINVI_PLAYWRIGHT_RUNNER_OUTPUT_DIR;

for (const viewport of [
  { name: 'pc', width: 1280, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]) {
  test(`관리자 버튼 변형별 포커스·hover·active·disabled 테두리 점검(${viewport.name} ${viewport.width})`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await setup(page);
    const ids = await mountFixture(page);
    const fixture = page.locator('#button-state-fixture');
    const shoot = async (state: string) => {
      if (output)
        await fixture.screenshot({
          path: join(output, `pinvi-admin-buttons-${viewport.name}-${state}.png`),
        });
    };
    await shoot('rest');

    const rest = new Map<string, Probe>();
    for (const id of ids) {
      const base = await probe(page, `#${id}`);
      rest.set(id, base);
      // 쉬는 상태에서 포커스 링이나 ring 그림자가 없다.
      expect(base.outlineStyle, id).toBe('none');
      // disabled도 같은 테두리 두께를 쓴다.
      expect((await probe(page, `#${id}-disabled`)).bw, `${id} disabled`).toBe(base.bw);
    }

    // Tab 포커스: 시작점에서 Tab을 눌러 차례로 지나간다(disabled는 건너뛴다).
    await page.locator('#fixture-start').focus();
    for (const id of ids) {
      await page.keyboard.press('Tab');
      await expect(page.locator(`#${id}`)).toBeFocused();
      const focused = await probe(page, `#${id}`);
      expect(focused.focusVisible, id).toBe(true);
      expect(
        {
          style: focused.outlineStyle,
          width: focused.outlineWidth,
          offset: focused.outlineOffset,
          shadow: focused.boxShadow,
          bw: focused.bw,
        },
        `${id} Tab 포커스`,
      ).toEqual({
        style: 'solid',
        width: '2px',
        offset: '2px',
        shadow: 'none',
        bw: rest.get(id)?.bw,
      });
      if (id === 'btn-outline' || id === 'legacy-refresh') await shoot(`focus-${id}`);
    }
    await page.locator('#fixture-start').focus();
    await shoot('focus-cleared');

    // hover·active(누르는 중): 포인터 상호작용은 포커스 링을 띄우지 않고 테두리 두께도 그대로다.
    for (const id of ids) {
      const button = page.locator(`#${id}`);
      await button.hover();
      const hovered = await probe(page, `#${id}`);
      expect(hovered.bw, `${id} hover`).toBe(rest.get(id)?.bw);
      expect(hovered.outlineStyle, `${id} hover`).toBe('none');
      if (id === 'btn-outline') await shoot('hover-outline');
      await page.mouse.down();
      const pressed = await probe(page, `#${id}`);
      expect(pressed.bw, `${id} active`).toBe(rest.get(id)?.bw);
      expect(pressed.focusVisible, `${id} active`).toBe(false);
      expect(pressed.outlineStyle === 'none' || pressed.outlineWidth === '0px', `${id} active outline`).toBe(true);
      expect(Math.abs(pressed.y - (rest.get(id)?.y ?? 0)), `${id} active 이동`).toBeLessThanOrEqual(1);
      expect(Math.abs(pressed.x - (rest.get(id)?.x ?? 0)), `${id} active 이동`).toBeLessThanOrEqual(1);
      if (id === 'btn-outline' || id === 'legacy-refresh') await shoot(`active-${id}`);
      await page.mouse.up();
    }

    // 셸 자신의 버튼(데스크톱 rail 접기, 모바일 메뉴 열기)도 Tab 포커스 때 2px 단일 outline이다.
    const shellButton = page.locator(
      viewport.width >= 1024
        ? '[data-slot="admin-shell-collapse"]'
        : '[data-slot="admin-shell-menu-button"]',
    );
    await shellButton.focus();
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Tab');
    await expect(shellButton).toBeFocused();
    const shellFocus = await shellButton.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        style: s.outlineStyle,
        width: s.outlineWidth,
        offset: s.outlineOffset,
        shadow: s.boxShadow,
        border: s.borderTopWidth,
      };
    });
    expect(shellFocus).toEqual({
      style: 'solid',
      width: '2px',
      offset: '2px',
      shadow: 'none',
      border: '0px',
    });
    if (output)
      await page.screenshot({
        path: join(output, `pinvi-admin-buttons-${viewport.name}-shell-focus.png`),
      });
  });
}

test('관리자 포커스 규칙은 사용자 화면에 걸리지 않는다', async ({ page }) => {
  await page.route(/.*\/auth\/oauth\/providers$/, (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: { providers: [{ provider: 'google', enabled: true }] } }),
    }),
  );
  await page.goto('/login');
  await expect(page.getByTestId('login-submit')).toBeVisible();
  expect(await page.locator('[data-pv-surface="admin"], [data-slot^="admin-shell"]').count()).toBe(
    0,
  );
  // 사용자 화면에 관리자 스코프 밖 동일 마크업을 심어도 관리자 outline이 붙지 않는다.
  await page.evaluate(() => {
    const button = document.createElement('button');
    button.id = 'user-probe';
    button.className = 'rounded-sm border border-hairline px-3 py-1 text-sm';
    button.textContent = 'probe';
    document.body.prepend(button);
  });
  await page.locator('#user-probe').focus();
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('Tab');
  await expect(page.locator('#user-probe')).toBeFocused();
  const outline = await page.locator('#user-probe').evaluate((el) => {
    const s = getComputedStyle(el);
    return { style: s.outlineStyle, color: s.outlineColor };
  });
  const adminFocus = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--kt-focus').trim(),
  );
  // 브라우저 기본(auto) 그대로이며 관리자 규칙(2px solid --kt-focus)이 아니다.
  expect(outline.style).not.toBe('solid');
  expect(adminFocus === '' || outline.color !== adminFocus).toBe(true);
});
