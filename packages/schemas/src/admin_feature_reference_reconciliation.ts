import { z } from 'zod';
import { Iso8601Schema } from './common';

const Sha256Schema = z.string().regex(/^[0-9a-f]{64}$/, 'SHA-256 hex 형식이어야 합니다.');
const UuidSchema = z.string().uuid();
const FeatureReferenceReconciliationStatusSchema = z.enum(['blocked', 'applied']);

/** Map M05 event를 검사한 append-only local 관측. */
export const AdminFeatureReferenceReconciliationAttemptSchema = z.object({
  event_id: UuidSchema,
  attempt_sequence: z.number().int().positive(),
  event_sequence: z.number().int().positive(),
  event_sha256: Sha256Schema,
  status: FeatureReferenceReconciliationStatusSchema,
  block_fingerprint_sha256: Sha256Schema.nullable().optional(),
  observation_root_sha256: Sha256Schema,
  observed_at: Iso8601Schema,
});
export type AdminFeatureReferenceReconciliationAttempt = z.infer<
  typeof AdminFeatureReferenceReconciliationAttemptSchema
>;

/** Map ACK 전에 commit되는 terminal local receipt. */
export const AdminFeatureReferenceReconciliationReceiptSchema = z.object({
  event_id: UuidSchema,
  event_sequence: z.number().int().positive(),
  event_sha256: Sha256Schema,
  action: z.enum(['rebind', 'detach']),
  old_feature_id: z.string(),
  old_feature_uuid: UuidSchema,
  replacement_feature_id: z.string().nullable().optional(),
  replacement_feature_uuid: UuidSchema.nullable().optional(),
  impact_root_sha256: Sha256Schema,
  impact_count: z.number().int().nonnegative(),
  receipt_sha256: Sha256Schema,
  applied_at: Iso8601Schema,
});
export type AdminFeatureReferenceReconciliationReceipt = z.infer<
  typeof AdminFeatureReferenceReconciliationReceiptSchema
>;

export const AdminFeatureReferenceReconciliationImpactSchema = z.object({
  event_id: UuidSchema,
  impact_index: z.number().int().nonnegative(),
  target_relation: z.enum(['trip_day_pois', 'curated_plan_pois', 'feature_suggestions']),
  target_id: UuidSchema,
  old_feature_id: z.string(),
  old_feature_uuid: UuidSchema,
  replacement_feature_id: z.string().nullable().optional(),
  replacement_feature_uuid: UuidSchema.nullable().optional(),
  outcome: z.enum(['rebind', 'detach', 'already_reconciled']),
  recorded_at: Iso8601Schema,
});
export type AdminFeatureReferenceReconciliationImpact = z.infer<
  typeof AdminFeatureReferenceReconciliationImpactSchema
>;

export const AdminFeatureReferenceReconciliationSummarySchema = z
  .object({
    event_id: UuidSchema,
    status: FeatureReferenceReconciliationStatusSchema,
    event_sequence: z.number().int().positive(),
    event_sha256: Sha256Schema,
    observed_at: Iso8601Schema,
    receipt: AdminFeatureReferenceReconciliationReceiptSchema.nullable().optional(),
    latest_attempt: AdminFeatureReferenceReconciliationAttemptSchema,
  })
  .superRefine((value, context) => {
    const applied = value.status === 'applied';
    const shapeValid = applied
      ? value.receipt != null && value.latest_attempt.status === 'applied'
      : value.receipt == null && value.latest_attempt.status === 'blocked';
    if (!shapeValid) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'M05 evidence status와 receipt/latest attempt가 일치하지 않습니다.',
      });
    }
  });
export type AdminFeatureReferenceReconciliationSummary = z.infer<
  typeof AdminFeatureReferenceReconciliationSummarySchema
>;

export const AdminFeatureReferenceReconciliationPagedResponseSchema = z.object({
  items: z.array(AdminFeatureReferenceReconciliationSummarySchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  limit: z.number().int().min(1).max(100),
});
export type AdminFeatureReferenceReconciliationPagedResponse = z.infer<
  typeof AdminFeatureReferenceReconciliationPagedResponseSchema
>;

export const AdminFeatureReferenceReconciliationDetailSchema = z
  .object({
    event_id: UuidSchema,
    status: FeatureReferenceReconciliationStatusSchema,
    receipt: AdminFeatureReferenceReconciliationReceiptSchema.nullable().optional(),
    attempts: z.array(AdminFeatureReferenceReconciliationAttemptSchema),
    impacts: z.array(AdminFeatureReferenceReconciliationImpactSchema),
  })
  .superRefine((value, context) => {
    const latest = value.attempts[0];
    const applied = value.status === 'applied';
    const shapeValid = applied
      ? value.receipt != null && latest?.status === 'applied'
      : value.receipt == null && latest?.status === 'blocked' && value.impacts.length === 0;
    if (!shapeValid) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'M05 detail의 receipt/attempt/impact terminal shape가 일치하지 않습니다.',
      });
    }
  });
export type AdminFeatureReferenceReconciliationDetail = z.infer<
  typeof AdminFeatureReferenceReconciliationDetailSchema
>;
