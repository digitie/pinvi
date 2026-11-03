import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SharedTripEditor } from '@/components/trips/SharedTripEditor';
import { ApiError } from '@pinvi/api-client';
import { TripResponseSchema } from '@pinvi/schemas';
const api = vi.hoisted(() => ({ updateShared: vi.fn(), getShared: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...await original<typeof import('@pinvi/api-client')>(), tripApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {}, sharedApiClient: {} }));
const trip = TripResponseSchema.parse({
  trip_id: '00000000-0000-4000-8000-000000000001',
  owner_user_id: '00000000-0000-4000-8000-000000000002',
  title: '원래 여행', description: null, region_hint: null,
  primary_region_code: null, primary_region_source: null,
  start_date: null, end_date: null, visibility: 'private', status: 'draft', version: 2,
  created_at: '2026-11-03T09:00:00+09:00', updated_at: '2026-11-03T09:00:00+09:00',
});
beforeEach(() => vi.clearAllMocks());
describe('공유 여행 정보 편집', () => {
  it('토큰과 표시 버전으로 저장하고 화면 데이터를 갱신한다', async () => {
    const onSaved = vi.fn();
    const updated = { ...trip, title: '바뀐 여행', version: 3 };
    api.updateShared.mockResolvedValue(updated);
    render(<SharedTripEditor tripId={trip.trip_id} token="share" trip={trip} onSaved={onSaved} />);
    fireEvent.change(screen.getByLabelText('여행 제목'), { target: { value: '바뀐 여행' } });
    fireEvent.click(screen.getByRole('button', { name: '여행 정보 저장' }));
    await screen.findByText('여행 정보를 저장했습니다.');
    expect(api.updateShared).toHaveBeenCalledWith(trip.trip_id, 'share', 2, {
      title: '바뀐 여행', description: '', region_hint: null,
    });
    expect(onSaved).toHaveBeenCalledWith(updated);
  });
  it('409 뒤 최신 정보로 갱신하고 새 버전으로 재시도한다', async () => {
    const latest = { ...trip, title: '다른 사람의 수정', version: 3 };
    api.updateShared.mockRejectedValueOnce(new ApiError('VERSION_CONFLICT', '충돌', 409));
    api.getShared.mockResolvedValue({ trip: latest });
    const onSaved = vi.fn();
    const { rerender } = render(<SharedTripEditor tripId={trip.trip_id} token="share" trip={trip} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '여행 정보 저장' }));
    fireEvent.click(await screen.findByRole('button', { name: '최신 정보 불러오기' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(latest));
    rerender(<SharedTripEditor tripId={trip.trip_id} token="share" trip={latest} onSaved={onSaved} />);
    api.updateShared.mockResolvedValue({ ...latest, version: 4 });
    fireEvent.click(screen.getByRole('button', { name: '여행 정보 저장' }));
    await screen.findByText('여행 정보를 저장했습니다.');
    expect(api.updateShared.mock.calls.map((args) => args[2])).toEqual([2, 3]);
  });
  it('401에서도 초안을 유지하고 새 탭 로그인을 안내한다', async () => {
    api.updateShared.mockRejectedValue(new ApiError('TOKEN_INVALID', '로그인 필요', 401));
    render(<SharedTripEditor tripId={trip.trip_id} token="share" trip={trip} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('여행 제목'), { target: { value: '잃으면 안 되는 초안' } });
    fireEvent.click(screen.getByRole('button', { name: '여행 정보 저장' }));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('여행 제목')).toHaveValue('잃으면 안 되는 초안');
    expect(screen.getByRole('link', { name: '새 탭에서 로그인' })).toHaveAttribute('target', '_blank');
  });
  it('저장 실패는 성공으로 보이지 않고 재시도를 허용한다', async () => {
    api.updateShared.mockRejectedValue(new Error('failed'));
    const onSaved = vi.fn();
    render(<SharedTripEditor tripId={trip.trip_id} token="share" trip={trip} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: '여행 정보 저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('저장하지 못했습니다.');
    expect(onSaved).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole('button', { name: '여행 정보 저장' })).toBeEnabled());
  });
});
