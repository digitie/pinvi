import { describe, expect, it } from 'vitest';
import { AttachmentResponseSchema } from './storage';

const planId = '11111111-1111-4111-8111-111111111111';
const poiId = '22222222-2222-4222-8222-222222222222';
const otherPlanId = '33333333-3333-4333-8333-333333333333';
const now = '2026-06-08T12:00:00+09:00';

const attachment = {
  attachment_id: '44444444-4444-4444-8444-444444444444',
  trip_id: null,
  trip_poi_id: null,
  curated_plan_id: planId,
  curated_poi_id: poiId,
  notice_plan_id: planId,
  notice_poi_id: poiId,
  source_attachment_id: null,
  bucket: 'tripmate-media',
  storage_key: 'curated/plan/image.jpg',
  original_filename: 'image.jpg',
  content_type: 'image/jpeg',
  byte_size: 1024,
  public_url: null,
  role: 'image',
  description: null,
  sort_order: 0,
  created_at: now,
  updated_at: now,
};

describe('AttachmentResponseSchema', () => {
  it('keeps curated fields and notice aliases in sync', () => {
    expect(AttachmentResponseSchema.parse(attachment)).toMatchObject({
      curated_plan_id: planId,
      curated_poi_id: poiId,
      notice_plan_id: planId,
      notice_poi_id: poiId,
    });
  });

  it('normalizes legacy notice aliases when canonical fields are absent', () => {
    const parsed = AttachmentResponseSchema.parse({
      ...attachment,
      curated_plan_id: undefined,
      curated_poi_id: undefined,
    });

    expect(parsed.curated_plan_id).toBe(planId);
    expect(parsed.curated_poi_id).toBe(poiId);
    expect(parsed.notice_plan_id).toBe(planId);
    expect(parsed.notice_poi_id).toBe(poiId);
  });

  it('rejects mismatched canonical and notice aliases', () => {
    expect(
      AttachmentResponseSchema.safeParse({
        ...attachment,
        notice_plan_id: otherPlanId,
      }).success,
    ).toBe(false);
  });
});
