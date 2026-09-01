import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * admin 전용 타이포 스케일의 **격리**를 잠근다(T-356).
 *
 * kor-travel-map admin의 7단 스케일(12/13.5/15/17/20/24/30px)을 이식하되, `text-xs`/`text-sm`/
 * `text-base`/`text-lg`/`text-xl`/`text-2xl`은 사용자 표면도 쓰는 이름이라 전역에서 바꾸면
 * 랜딩·여행·지도 화면의 활자가 통째로 흔들린다(DESIGN.md Hallmark 잠금 대상).
 *
 * 그래서 `@theme`(전역)에는 pinvi에 **이름이 없던** 두 단(`2xs`, `md`)만 두고, 나머지는
 * `[data-pv-surface='admin']` subtree에서 변수만 가린다. 이 파일은 그 경계가 무너지지 않았는지
 * globals.css를 직접 읽어 검사한다 — 전역 `@theme`에 `--text-sm` 한 줄이 새로 들어가는 순간
 * 사용자 표면이 조용히 회귀하기 때문이다.
 */
const CSS = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');

function block(startPattern: RegExp): string {
  const match = startPattern.exec(CSS);
  if (!match) throw new Error(`블록을 찾지 못했다: ${String(startPattern)}`);
  const from = match.index + match[0].length;
  const end = CSS.indexOf('\n}', from);
  return CSS.slice(from, end);
}

const THEME = block(/@theme\s*\{/);
const ADMIN_SCOPE = block(/\[data-pv-surface='admin'\]\s*\{/);

/** 사용자 표면과 이름이 겹쳐 전역에서 바꾸면 안 되는 단계. */
const SHARED_STEPS = ['xs', 'sm', 'base', 'lg', 'xl', '2xl'] as const;
/** pinvi에 원래 이름이 없어 전역 추가가 안전한 단계. */
const ADMIN_ONLY_STEPS = ['2xs', 'md'] as const;

describe('admin 타이포 스케일 격리', () => {
  it('공유 이름은 전역 @theme에서 재정의하지 않는다 (사용자 표면 보호)', () => {
    for (const step of SHARED_STEPS) {
      expect(
        THEME.includes(`--text-${step}:`),
        `--text-${step} 가 전역 @theme에 있다 — 사용자 표면 활자가 함께 바뀐다. ` +
          `admin에서만 바꾸려면 [data-pv-surface='admin'] 블록으로 옮겨라.`,
      ).toBe(false);
    }
  });

  it('공유 이름은 admin scope에서 KTM 값으로 재정의한다', () => {
    const expected: Record<string, string> = {
      xs: '0.84375rem',
      sm: '0.9375rem',
      base: '0.9375rem',
      lg: '1.25rem',
      xl: '1.5rem',
      '2xl': '1.875rem',
    };
    for (const [step, value] of Object.entries(expected)) {
      expect(ADMIN_SCOPE).toContain(`--text-${step}: ${value}`);
    }
  });

  it('line-height도 함께 재정의한다 (유틸이 두 변수를 각각 읽는다)', () => {
    for (const step of SHARED_STEPS) {
      expect(
        ADMIN_SCOPE.includes(`--text-${step}--line-height:`),
        `--text-${step}--line-height 가 없으면 크기만 바뀌고 행간은 pinvi 기본이 남는다.`,
      ).toBe(true);
    }
  });

  it('pinvi에 이름이 없던 단계만 전역에 둔다', () => {
    for (const step of ADMIN_ONLY_STEPS) {
      expect(THEME).toContain(`--text-${step}:`);
    }
  });

  it('KTM 7단 스케일 값이 전부 존재한다', () => {
    // 12 / 13.5 / 15 / 17 / 20 / 24 / 30 px
    const all = THEME + ADMIN_SCOPE;
    for (const value of ['0.75rem', '0.84375rem', '0.9375rem', '1.0625rem', '1.25rem', '1.5rem', '1.875rem']) {
      expect(all).toContain(value);
    }
  });
});
