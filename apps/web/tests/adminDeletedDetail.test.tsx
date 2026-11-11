import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AdminTripDetailPage from '@/app/(admin)/admin/trips/[trip_id]/page';
import AdminPoiDetailPage from '@/app/(admin)/admin/pois/[poi_id]/page';

const mocks = vi.hoisted(() => ({
  redirect: vi.fn(),
  deleteTrip: vi.fn().mockResolvedValue({ action: 'delete', affected: {} }),
  deletePoi: vi.fn().mockResolvedValue({ action: 'delete', affected: {} }),
}));
vi.mock('next/navigation', () => ({
  redirect: mocks.redirect,
  useParams: () => ({ trip_id: 'trip', poi_id: 'poi' }),
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  const trip = {
    trip_id: 'trip',
    owner_user_id: 'owner',
    owner_email_masked: 'o***@example.com',
    title: '삭제 전 여행',
    description: null,
    region_hint: null,
    primary_region_code: null,
    primary_region_source: null,
    start_date: null,
    end_date: null,
    visibility: 'private',
    status: 'draft',
    version: 1,
    day_count: 0,
    poi_count: 0,
    companion_count: 0,
    share_link_count: 0,
    created_at: '2026-11-11T00:00:00Z',
    updated_at: '2026-11-11T00:00:00Z',
    companions: [],
    days: [],
    pois: [],
    attachments: [],
    share_links: [],
    recent_audit: [],
  };
  const poi = {
    attachment_id: 'poi',
    trip_id: 'trip',
    trip_title: '여행',
    owner_user_id: 'owner',
    owner_email_masked: 'o***@example.com',
    day_index: 1,
    sort_order: 'a0',
    feature_id: null,
    feature_label: null,
    feature_link_broken_at: null,
    version: 1,
    created_at: '2026-11-11T00:00:00Z',
    updated_at: '2026-11-11T00:00:00Z',
    added_by_user_id: 'owner',
    added_by_email_masked: 'o***@example.com',
    feature_snapshot: {},
    custom_marker_color: null,
    custom_marker_icon: null,
    planned_arrival_at: null,
    planned_departure_at: null,
    user_note: null,
    budget_amount: null,
    actual_amount: null,
    currency: 'KRW',
    user_url: null,
    recent_audit: [],
  };
  const impact = {
    target_type: 'trip',
    target_id: 'trip',
    trip_id: 'trip',
    day_index: null,
    counts: {},
    policy_options: {},
    warnings: [],
  };
  return {
    ...actual,
    adminApi: () => ({
      listTrips: () => Promise.resolve({ items: [] }),
      getTrip: () => Promise.resolve(trip),
      getPoi: () => Promise.resolve(poi),
      getTripOperationImpact: () => Promise.resolve(impact),
      getPoiOperationImpact: () =>
        Promise.resolve({ ...impact, target_type: 'poi', target_id: 'poi' }),
      deleteTrip: mocks.deleteTrip,
      deletePoi: mocks.deletePoi,
    }),
  };
});
beforeEach(() => vi.clearAllMocks());
describe('관리자 상세 삭제 성공 후 목록 복귀', () => {
  it.each([
    ['trip', '/admin/trips', AdminTripDetailPage],
    ['poi', '/admin/pois', AdminPoiDetailPage],
  ] as const)('%s 삭제 후 상세와 운영 모달에 남지 않는다', async (kind, list, Page) => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(await screen.findByTestId('admin-' + kind + '-delete-open'));
    await user.type(screen.getByTestId('admin-' + kind + '-operation-reason'), '삭제 승인');
    await user.click(screen.getByTestId('admin-' + kind + '-operation-confirm'));
    await waitFor(() =>
      expect(mocks[kind === 'trip' ? 'deleteTrip' : 'deletePoi']).toHaveBeenCalledTimes(1),
    );
    await waitFor(() => expect(mocks.redirect).toHaveBeenCalledWith(list));
  });
});
