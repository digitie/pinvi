import { describe, expect, it } from 'vitest';
import type { UserConsent } from '@tripmate/schemas';
import { hasLocationConsent, locationConsentItems } from '@/lib/locationConsent';

function consent(over: Partial<UserConsent> & { consent_type: UserConsent['consent_type'] }): UserConsent {
  return {
    version: 'v1.0',
    agreed_at: '2026-06-10T00:00:00Z',
    withdrawn_at: null,
    ...over,
  };
}

describe('locationConsent', () => {
  it('hasLocationConsent: 2종 모두 유효해야 true', () => {
    expect(
      hasLocationConsent([
        consent({ consent_type: 'lbs_tos' }),
        consent({ consent_type: 'location_collection' }),
      ])
    ).toBe(true);
  });

  it('hasLocationConsent: 하나 철회되면 false', () => {
    expect(
      hasLocationConsent([
        consent({ consent_type: 'lbs_tos' }),
        consent({ consent_type: 'location_collection', withdrawn_at: '2026-06-11T00:00:00Z' }),
      ])
    ).toBe(false);
  });

  it('hasLocationConsent: 하나 없으면 false', () => {
    expect(hasLocationConsent([consent({ consent_type: 'lbs_tos' })])).toBe(false);
    expect(hasLocationConsent([])).toBe(false);
  });

  it('locationConsentItems: 2종 v1.0', () => {
    expect(locationConsentItems()).toEqual([
      { consent_type: 'lbs_tos', version: 'v1.0' },
      { consent_type: 'location_collection', version: 'v1.0' },
    ]);
  });
});
