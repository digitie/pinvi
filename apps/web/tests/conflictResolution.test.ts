import { describe, expect, it } from 'vitest';
import { hasPatchFields, pickConflictPatch, resolveConflictKeys } from '@/lib/conflictResolution';

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

  describe('resolveConflictKeys', () => {
    it('다이얼로그에 없는 patch 필드는 mine으로 carry-through 한다 (drift 무손실)', () => {
      // patch에 description이 있으나 conflict 다이얼로그 필드 목록에는 없음(drift).
      const patchKeys = ['title', 'status', 'description'];
      const displayedKeys = ['title', 'status'];
      const selectedMineKeys = ['title']; // status는 서버 값 선택
      expect(resolveConflictKeys(patchKeys, displayedKeys, selectedMineKeys).sort()).toEqual(
        ['description', 'title'].sort(),
      );
    });

    it('표시된 필드 중 미선택(서버 값)은 제외하고, 선택된 mine만 남긴다', () => {
      expect(resolveConflictKeys(['title', 'status'], ['title', 'status'], ['status'])).toEqual([
        'status',
      ]);
    });

    it('patch에 없는 selected key는 무시한다', () => {
      expect(resolveConflictKeys(['title'], ['title'], ['title', 'ghost'])).toEqual(['title']);
    });
  });
});
