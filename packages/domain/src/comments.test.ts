import { describe, expect, it } from 'vitest';
import { canDeleteComment } from './comments';

describe('comments', () => {
  it('canDeleteComment: 본인 댓글만', () => {
    expect(canDeleteComment({ author_user_id: 'u1' }, 'u1')).toBe(true);
    expect(canDeleteComment({ author_user_id: 'u2' }, 'u1')).toBe(false);
    expect(canDeleteComment({ author_user_id: null }, 'u1')).toBe(false);
    expect(canDeleteComment({ author_user_id: 'u1' }, null)).toBe(false);
  });
});
