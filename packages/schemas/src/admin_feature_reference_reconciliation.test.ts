import { describe, expect, it } from 'vitest';

import {
  AdminFeatureReferenceReconciliationDetailSchema,
  AdminFeatureReferenceReconciliationSummarySchema,
} from './admin_feature_reference_reconciliation';

const event_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const attempt = {
  event_id,
  attempt_sequence: 1,
  event_sequence: 1,
  event_sha256: 'a'.repeat(64),
  status: 'applied',
  block_fingerprint_sha256: null,
  observation_root_sha256: 'b'.repeat(64),
  observed_at: '2026-08-21T10:00:00+09:00',
};
const receipt = {
  event_id,
  event_sequence: 1,
  event_sha256: 'a'.repeat(64),
  action: 'rebind',
  old_feature_id: 'feature-old',
  old_feature_uuid: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
  replacement_feature_id: 'feature-new',
  replacement_feature_uuid: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  impact_root_sha256: 'e'.repeat(64),
  impact_count: 0,
  receipt_sha256: 'f'.repeat(64),
  applied_at: '2026-08-21T10:00:00+09:00',
};

describe('AdminFeatureReferenceReconciliation evidence shape', () => {
  it('rejects applied summary without a receipt', () => {
    expect(
      AdminFeatureReferenceReconciliationSummarySchema.safeParse({
        event_id,
        status: 'applied',
        event_sequence: 1,
        event_sha256: 'a'.repeat(64),
        observed_at: '2026-08-21T10:00:00+09:00',
        receipt: null,
        latest_attempt: attempt,
      }).success,
    ).toBe(false);
  });

  it('rejects blocked detail that carries terminal evidence', () => {
    expect(
      AdminFeatureReferenceReconciliationDetailSchema.safeParse({
        event_id,
        status: 'blocked',
        receipt,
        attempts: [{ ...attempt, status: 'blocked', block_fingerprint_sha256: 'c'.repeat(64) }],
        impacts: [],
      }).success,
    ).toBe(false);
  });
});
