import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { AnchorHTMLAttributes } from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '@/components/app/AppShell';

const state = vi.hoisted(() => ({ path: '/map', mobile: false }));
vi.mock('next/navigation', () => ({ usePathname: () => state.path }));
vi.mock('next/link', () => ({
  default: ({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props} />
  ),
}));
vi.mock('@/lib/useMobileWebLayout', () => ({ useMobileWebLayout: () => state.mobile }));

beforeEach(() => {
  state.path = '/map';
  state.mobile = false;
});

/**
 * 소유자 요청 2026-11-17 "지도도 전체화면으로" — 탐색 지도(/map)는 셸이 창 높이에 고정되고 본문 여백이 없다.
 * 상단 바는 데스크톱에서만 얇게, 모바일은 숨긴다(이동은 하단 탭바). jsdom은 레이아웃을 계산하지 않으므로
 * 그 경계를 만드는 class·CSS 규칙을 잠근다(실제 크기는 live e2e CORE-049가 본다).
 */
describe('앱 셸 — 전체 화면 탐색 지도(/map)', () => {
  it('셸은 창 높이(h-dvh)에 고정되고 페이지가 스크롤되지 않는다', () => {
    const { container } = render(<AppShell>지도</AppShell>);
    const shell = container.firstElementChild as HTMLElement;
    expect(shell).toHaveAttribute('data-explore-map', 'on');
    expect(shell.className).toMatch(/\bh-dvh\b/);
    expect(shell.className).toMatch(/\boverflow-hidden\b/);
    expect(shell.className).not.toMatch(/\bmin-h-dvh\b/);
  });

  it('본문은 여백 없이 지도가 꽉 찬다(px/pt 없음)', () => {
    render(<AppShell>지도</AppShell>);
    const classes = screen.getByRole('main').className.split(/\s+/);
    expect(classes).toContain('app-shell-main-map');
    // 일반 본문 class(하단 여유 +1.5rem)와 좌우·위 여백 유틸이 없다.
    expect(classes).not.toContain('app-shell-main');
    expect(classes.filter((c) => /^(?:\w+:)?(?:px|pt|py|p)-/.test(c))).toEqual([]);
  });

  it('상단 바는 데스크톱(lg)에서만 얇게 보이고, 모바일 탭바는 그대로다', () => {
    render(<AppShell>지도</AppShell>);
    const header = screen.getByRole('banner');
    expect(header.className).toMatch(/\bhidden\b/);
    expect(header.className).toMatch(/\blg:block\b/);
    expect(header.className).toContain('app-shell-map-header');
    expect(header.firstElementChild?.className).toMatch(/\bpy-1\b/);
    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeInTheDocument();
    expect(screen.getByTestId('app-nav--map')).toHaveAttribute('aria-current', 'page');
  });

  it('다른 경로(/trips, /map 하위 아님)는 예전 셸 그대로다', () => {
    state.path = '/trips';
    const { container } = render(<AppShell>목록</AppShell>);
    const shell = container.firstElementChild as HTMLElement;
    expect(shell).not.toHaveAttribute('data-explore-map');
    expect(shell.className).toMatch(/\bmin-h-dvh\b/);
    expect(screen.getByRole('main').className.split(/\s+/)).toContain('app-shell-main');
    expect(screen.getByRole('banner').className).not.toMatch(/\bhidden\b/);
  });
});

describe('전체 화면 지도 CSS — 모바일 탭바 자리만 비운다', () => {
  const CSS = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');
  const rules = (selector: string): string[] => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return [...CSS.matchAll(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, 'g'))].map((m) => m[1] ?? '');
  };

  it('모바일은 탭바 높이(+safe area)만, 데스크톱은 0', () => {
    const bodies = rules('.app-shell-main-map');
    expect(bodies.length).toBeGreaterThanOrEqual(3);
    // 기본(모바일)과 넓은 화면 폰 보정은 탭바 높이만 — 일반 본문의 +1.5rem 여유는 없다.
    const mobile = bodies.filter((b) => b.includes('--app-tabbar-h'));
    expect(mobile.length).toBeGreaterThanOrEqual(2);
    for (const body of mobile) expect(body).not.toContain('1.5rem');
    expect(bodies.some((b) => /padding-bottom:\s*0/.test(b))).toBe(true);
  });

  it('넓은 화면 폰(모바일 셸)에서도 지도 상단 바를 숨긴다', () => {
    expect(CSS).toMatch(
      /\[data-mobile-layout='on'\] \.app-shell-map-header\s*\{\s*display:\s*none;/,
    );
  });
});
