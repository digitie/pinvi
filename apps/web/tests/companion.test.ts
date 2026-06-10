import { describe, expect, it } from 'vitest';
import { companionDisplayName, companionJoined } from '@/lib/companion';

describe('companion', () => {
  it('companionDisplayName: nickname > email > fallback', () => {
    expect(companionDisplayName({ invited_nickname: '민수', invited_email: 'a@b.c' })).toBe('민수');
    expect(companionDisplayName({ invited_nickname: null, invited_email: 'a@b.c' })).toBe('a@b.c');
    expect(companionDisplayName({ invited_nickname: null, invited_email: null })).toBe(
      '알 수 없는 사용자'
    );
  });

  it('companionJoined: joined_at 유무', () => {
    expect(companionJoined({ joined_at: '2026-06-10T00:00:00Z' })).toBe(true);
    expect(companionJoined({ joined_at: null })).toBe(false);
  });
});
