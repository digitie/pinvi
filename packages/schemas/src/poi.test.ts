import { describe, expect, it } from 'vitest';
import { PoiRiseSetResponseSchema } from './poi';

describe('POI rise set response schema', () => {
  it('accepts success and pending KASI rise set states', () => {
    const success = PoiRiseSetResponseSchema.parse({
      status: 'success',
      locdate: '2026-06-02',
      sunrise_at: '2026-06-02T05:10:00+09:00',
      sunset_at: '2026-06-02T19:39:00+09:00',
      moonrise_at: null,
      moonset_at: null,
      fetched_at: '2026-06-01T21:00:00Z',
      updated_at: '2026-06-01T21:00:00Z',
    });
    const pending = PoiRiseSetResponseSchema.parse({
      status: 'pending_fetch',
      locdate: '2026-06-02',
      sunrise_at: null,
      sunset_at: null,
      moonrise_at: null,
      moonset_at: null,
      fetched_at: null,
      updated_at: '2026-06-01T21:00:00Z',
    });

    expect(success.status).toBe('success');
    expect(pending.status).toBe('pending_fetch');
  });
});
