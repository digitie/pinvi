import { describe, expect, it } from 'vitest';
import { AdminFeatureRequestApproveSchema } from './admin_feature_request';

describe('AdminFeatureRequestApproveSchema', () => {
  it('rejects marker colors outside the Map palette', () => {
    expect(
      AdminFeatureRequestApproveSchema.safeParse({
        access_reason: '검토',
        marker_color: 'P-99',
      }).success,
    ).toBe(false);
  });

  it('accepts the last Map palette marker', () => {
    expect(
      AdminFeatureRequestApproveSchema.parse({
        access_reason: '검토',
        marker_color: 'P-16',
      }).marker_color,
    ).toBe('P-16');
  });
});
