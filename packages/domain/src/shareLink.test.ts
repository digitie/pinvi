import { describe, expect, it } from 'vitest';
import { shareLinkStatus } from './shareLink';

const NOW = Date.parse('2026-06-10T00:00:00Z');

describe('shareLink', () => {
  it('revoked 우선', () => {
    expect(
      shareLinkStatus({ expires_at: null, revoked_at: '2026-06-09T00:00:00Z' }, NOW)
    ).toBe('revoked');
  });

  it('만료 시각 지나면 expired', () => {
    expect(shareLinkStatus({ expires_at: '2026-06-09T00:00:00Z', revoked_at: null }, NOW)).toBe(
      'expired'
    );
  });

  it('만료 안 됐고 철회 안 됐으면 active', () => {
    expect(shareLinkStatus({ expires_at: '2026-06-11T00:00:00Z', revoked_at: null }, NOW)).toBe(
      'active'
    );
    expect(shareLinkStatus({ expires_at: null, revoked_at: null }, NOW)).toBe('active');
  });
});
