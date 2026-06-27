import { describe, expect, it } from 'vitest';
import { hasPatchFields, pickConflictPatch } from '@/lib/conflictResolution';

describe('conflictResolution', () => {
  it('선택한 mine 필드만 재시도 patch로 남긴다', () => {
    const patch = {
      title: '내 제목',
      region_hint: null,
      status: 'planned',
    };

    expect(pickConflictPatch(patch, ['title', 'status'])).toEqual({
      title: '내 제목',
      status: 'planned',
    });
  });

  it('서버 값을 선택해 빈 patch가 되면 저장하지 않는다', () => {
    expect(hasPatchFields({})).toBe(false);
    expect(hasPatchFields({ user_note: null })).toBe(true);
  });
});
