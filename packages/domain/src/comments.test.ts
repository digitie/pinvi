import { describe, expect, it } from 'vitest';
import { canDeleteComment } from './comments';

describe('comments', () => {
  it('canDeleteComment: 소유자도 다른 작성자의 댓글을 삭제한다', () => {
    expect(canDeleteComment({ author_user_id: 'other' }, 'owner', 'owner')).toBe(true);
    expect(canDeleteComment({ author_user_id: 'other' }, 'reader', 'owner')).toBe(false);
    expect(canDeleteComment({ author_user_id: null }, null, null)).toBe(false);
  });
  it('canDeleteComment: 본인 댓글만', () => {
    expect(canDeleteComment({ author_user_id: 'u1' }, 'u1')).toBe(true);
    expect(canDeleteComment({ author_user_id: 'u2' }, 'u1')).toBe(false);
    expect(canDeleteComment({ author_user_id: null }, 'u1')).toBe(false);
    expect(canDeleteComment({ author_user_id: 'u1' }, null)).toBe(false);
  });
});
