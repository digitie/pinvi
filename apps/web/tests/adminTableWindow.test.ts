import { describe, expect, it } from 'vitest';
import { computeSpacerWindow } from '@/lib/adminTableWindow';

describe('computeSpacerWindow', () => {
  it('빈 윈도우는 스페이서 0', () => {
    expect(computeSpacerWindow([], 0)).toEqual({ paddingTop: 0, paddingBottom: 0 });
  });

  it('첫 항목 start = 상단 스페이서, totalSize - 마지막 end = 하단 스페이서', () => {
    const items = [
      { start: 100, end: 141 },
      { start: 141, end: 182 },
    ];
    expect(computeSpacerWindow(items, 1000)).toEqual({ paddingTop: 100, paddingBottom: 818 });
  });

  it('상단(첫 항목부터)일 때 상단 스페이서 0', () => {
    const items = [
      { start: 0, end: 41 },
      { start: 41, end: 82 },
    ];
    expect(computeSpacerWindow(items, 82)).toEqual({ paddingTop: 0, paddingBottom: 0 });
  });

  it('음수는 0으로 클램프', () => {
    const items = [{ start: -5, end: 10 }];
    expect(computeSpacerWindow(items, 5)).toEqual({ paddingTop: 0, paddingBottom: 0 });
  });
});
