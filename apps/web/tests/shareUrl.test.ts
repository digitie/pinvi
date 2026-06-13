import { describe, expect, it } from 'vitest';
import { buildShareUrl } from '@/lib/shareUrl';

describe('shareUrl', () => {
  it('buildShareUrl: origin + /shared/{tripId}/{token}', () => {
    expect(buildShareUrl('https://pinvi.app', 'trip-1', 'tok-9')).toBe(
      'https://pinvi.app/shared/trip-1/tok-9'
    );
  });
});
