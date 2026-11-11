import { describe, expect, it } from 'vitest';
import { apiErrorCode, apiErrorMessage } from '../e2e-live/helpers/apiError';

// #728: NTF-003/NTF-010 read `body.detail.code`, but PinVi rewraps HTTPException.detail into the
// `error` envelope (apps/api/app/core/errors.py, docs/api/common.md §2.2) — the code was always undefined.
describe('live spec API error envelope', () => {
  it('reads the code and message from the standard envelope', () => {
    const verifyFailed = { error: { code: 'invalid_chat', message: 'telegram verify 실패: invalid_chat' } };
    expect(apiErrorCode(verifyFailed)).toBe('invalid_chat');
    expect(apiErrorMessage(verifyFailed)).toBe('telegram verify 실패: invalid_chat');
    const limit = { error: { code: 'MAX_TARGETS_REACHED', message: 'x', reason: 'max_targets_reached' } };
    expect(apiErrorCode(limit)).toBe('MAX_TARGETS_REACHED');
  });

  it('does not fall back to the route-internal detail shape', () => {
    expect(apiErrorCode({ detail: { code: 'invalid_chat' } })).toBeUndefined();
    expect(apiErrorCode({ code: 'invalid_chat' })).toBeUndefined();
  });

  it('tolerates non-envelope bodies', () => {
    for (const body of [undefined, null, {}, 'text', { error: 'x' }, { error: { code: 3 } }]) {
      expect(apiErrorCode(body)).toBeUndefined();
    }
  });
});
