import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import AdminUserDetailPage from '@/app/(admin)/admin/users/[user_id]/page';
import AdminTripDetailPage from '@/app/(admin)/admin/trips/[trip_id]/page';
import AdminPoiDetailPage from '@/app/(admin)/admin/pois/[poi_id]/page';

const mocks = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock('next/navigation', () => ({
  redirect: mocks.redirect,
  useParams: () => ({ user_id: 'missing-user', trip_id: 'missing-trip', poi_id: 'missing-poi' }),
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock('@pinvi/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@pinvi/api-client')>();
  const missing = () =>
    Promise.reject(new actual.ApiError('NOT_FOUND', '대상을 찾을 수 없습니다', 404));
  return {
    ...actual,
    adminApi: () => ({
      getUser: missing,
      getTrip: missing,
      getPoi: missing,
      getAvatarSettings: () => Promise.resolve({}),
      listUserSessions: () => Promise.resolve({ items: [] }),
    }),
  };
});

beforeEach(() => vi.clearAllMocks());
describe('관리자 상세 대상이 사라졌을 때 목록 복귀', () => {
  it.each([
    ['/admin/users', AdminUserDetailPage],
    ['/admin/trips', AdminTripDetailPage],
    ['/admin/pois', AdminPoiDetailPage],
  ] as const)('%s 상세404는 로딩화면에 머무르지 않는다', async (list, Page) => {
    render(<Page />);
    await waitFor(() => expect(mocks.redirect).toHaveBeenCalledWith(list));
  });
});
