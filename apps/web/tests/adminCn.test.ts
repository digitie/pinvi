import { describe, expect, it } from 'vitest';
import { cn } from '@/lib/admin/cn';

/**
 * `cn`의 그룹 병합을 잠근다(T-356). tailwind-merge는 커스텀 유틸 이름을 기본 추론으로 알지 못하므로
 * admin `@theme`가 새로 만든 이름이 preset 이름과 같은 축에서 충돌할 때 뒤에 온 쪽이 이겨야 한다.
 * 이 계약이 깨지면 variant override가 조용히 무시되어 시각 회귀로만 드러난다.
 */
describe('admin cn', () => {
  it('border-radius 축에서 커스텀 radius가 preset radius를 덮는다', () => {
    expect(cn('rounded-sm', 'rounded-control')).toBe('rounded-control');
    expect(cn('rounded-control', 'rounded-sm')).toBe('rounded-sm');
    expect(cn('rounded-panel', 'rounded-control')).toBe('rounded-control');
  });

  it('height 축에서 h-control이 숫자 height를 덮는다', () => {
    expect(cn('h-10', 'h-control')).toBe('h-control');
    expect(cn('h-control', 'h-control-sm')).toBe('h-control-sm');
  });

  it('font-size 축에서 text-2xs/text-md가 preset 크기를 덮는다', () => {
    expect(cn('text-sm', 'text-2xs')).toBe('text-2xs');
    expect(cn('text-2xs', 'text-md')).toBe('text-md');
  });

  it('font-size와 text 색을 서로 다른 축으로 유지한다 (색이 사라지면 안 된다)', () => {
    expect(cn('text-2xs', 'text-ink')).toBe('text-2xs text-ink');
    expect(cn('text-ink', 'text-md')).toBe('text-ink text-md');
  });

  it('width 축에서 w-rail이 숫자 width를 덮는다', () => {
    expect(cn('w-80', 'w-rail')).toBe('w-rail');
  });

  it('조건부/배열 입력을 clsx 규칙대로 평탄화한다', () => {
    expect(cn('a', false && 'b', ['c', null], undefined)).toBe('a c');
  });

  it('서로 다른 축은 함께 남긴다', () => {
    expect(cn('rounded-control', 'h-control', 'text-2xs')).toBe(
      'rounded-control h-control text-2xs',
    );
  });
});
