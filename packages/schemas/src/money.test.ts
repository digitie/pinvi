import { describe, expect, it } from 'vitest';
import { AdminPoiDetailSchema } from './admin';
import { NonNegativeDecimalStringSchema } from './common';
import { NoticePoiSchema } from './notice-plan';
import { PoiResponseSchema } from './poi';
import { TripViewPoiSchema } from './trip';

const ids = {
  attachment: '11111111-1111-4111-8111-111111111111',
  trip: '22222222-2222-4222-8222-222222222222',
  user: '33333333-3333-4333-8333-333333333333',
  noticePoi: '44444444-4444-4444-8444-444444444444',
  noticePlan: '55555555-5555-4555-8555-555555555555',
};
const now = '2026-06-08T12:00:00+09:00';

const roundTrip = (
  schema: { parse: (value: unknown) => unknown },
  value: unknown,
): unknown => {
  const parsed = schema.parse(value);
  return schema.parse(JSON.parse(JSON.stringify(parsed)));
};

describe('money response schemas', () => {
  it('accept decimal strings and round-trip without numeric coercion', () => {
    const adminPoi = {
      attachment_id: ids.attachment,
      trip_id: ids.trip,
      trip_title: '부산 여행',
      owner_user_id: ids.user,
      owner_email_masked: 'b***@tripmate.test',
      day_index: 1,
      sort_order: 'a0',
      feature_id: 'place:abc123',
      feature_label: '광안리',
      feature_link_broken_at: null,
      version: 1,
      created_at: now,
      updated_at: now,
      added_by_user_id: ids.user,
      added_by_email_masked: 'b***@tripmate.test',
      feature_snapshot: { name: '광안리' },
      custom_marker_color: null,
      custom_marker_icon: null,
      planned_arrival_at: null,
      planned_departure_at: null,
      user_note: null,
      budget_amount: '12000.00',
      actual_amount: '10000.50',
      currency: 'KRW',
      user_url: null,
      recent_audit: [],
    };
    const poiResponse = {
      attachment_id: ids.attachment,
      trip_id: ids.trip,
      day_index: 1,
      sort_order: 'a0',
      feature_id: 'place:abc123',
      feature_link_broken_at: null,
      feature_snapshot: { name: '광안리' },
      custom_marker_color: null,
      custom_marker_icon: null,
      planned_arrival_at: null,
      planned_departure_at: null,
      user_note: null,
      budget_amount: '12000.00',
      actual_amount: '10000.50',
      currency: 'KRW',
      user_url: null,
      version: 1,
      created_at: now,
      updated_at: now,
    };
    const tripViewPoi = {
      poi_id: ids.attachment,
      feature_id: 'place:abc123',
      sort_order: 'a0',
      title: '광안리',
      feature: { name: '광안리' },
      marker_color: null,
      marker_icon: null,
      is_broken: false,
      user_note: null,
      planned_arrival_at: null,
      planned_departure_at: null,
      budget_amount: '12000.00',
      actual_amount: '10000.50',
      currency: 'KRW',
      user_url: null,
      feature_link_broken_at: null,
      version: 1,
      created_at: now,
      updated_at: now,
    };
    const noticePoi = {
      notice_poi_id: ids.noticePoi,
      notice_plan_id: ids.noticePlan,
      day_index: 1,
      sort_order: 'a0',
      feature_id: 'place:abc123',
      feature_snapshot: { name: '광안리' },
      memo: null,
      budget_amount: '12000.00',
      currency: 'KRW',
      custom_marker_color: null,
      custom_marker_icon: null,
      version: 1,
      created_at: now,
      updated_at: now,
    };

    expect(roundTrip(AdminPoiDetailSchema, adminPoi)).toMatchObject({
      budget_amount: '12000.00',
      actual_amount: '10000.50',
    });
    expect(roundTrip(PoiResponseSchema, poiResponse)).toMatchObject({
      budget_amount: '12000.00',
      actual_amount: '10000.50',
    });
    expect(roundTrip(TripViewPoiSchema, tripViewPoi)).toMatchObject({
      budget_amount: '12000.00',
      actual_amount: '10000.50',
    });
    expect(roundTrip(NoticePoiSchema, noticePoi)).toMatchObject({
      budget_amount: '12000.00',
    });
  });

  it('rejects numeric and exponential money response values', () => {
    expect(NonNegativeDecimalStringSchema.safeParse('12000.00').success).toBe(true);
    expect(NonNegativeDecimalStringSchema.safeParse('1e3').success).toBe(false);
    expect(NonNegativeDecimalStringSchema.safeParse('-1.00').success).toBe(false);
    expect(
      AdminPoiDetailSchema.safeParse({
        attachment_id: ids.attachment,
        trip_id: ids.trip,
        trip_title: '부산 여행',
        owner_user_id: ids.user,
        owner_email_masked: 'b***@tripmate.test',
        day_index: 1,
        sort_order: 'a0',
        feature_id: 'place:abc123',
        feature_label: null,
        feature_link_broken_at: null,
        version: 1,
        created_at: now,
        updated_at: now,
        added_by_user_id: ids.user,
        added_by_email_masked: null,
        feature_snapshot: {},
        custom_marker_color: null,
        custom_marker_icon: null,
        planned_arrival_at: null,
        planned_departure_at: null,
        user_note: null,
        budget_amount: 12000,
        actual_amount: null,
        currency: 'KRW',
        user_url: null,
        recent_audit: [],
      }).success,
    ).toBe(false);
  });
});
