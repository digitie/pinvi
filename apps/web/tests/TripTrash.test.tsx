import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TripTrash } from '@/components/trips/TripTrash';
const api = vi.hoisted(() => ({ listPage: vi.fn(), restore: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...await original<typeof import('@pinvi/api-client')>(), tripApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
const trip = { trip_id: 'trip1', title: '복원할 여행', start_date: null, end_date: null };
const page = { items: [trip], has_more: false, cursor: null };
beforeEach(() => {
  vi.clearAllMocks();
  api.listPage.mockResolvedValue(page);
});

describe('휴지통', () => {
  it('복원이 성공하면 목록을 다시 읽고 완료를 표시한다', async () => {
    api.restore.mockResolvedValue({});
    render(<TripTrash />);
    const button = await screen.findByRole('button', { name: '복원할 여행 복원' });
    api.listPage.mockResolvedValue({ items: [], has_more: false, cursor: null });
    fireEvent.click(button);
    await screen.findByRole('status');
    await screen.findByText('휴지통에 여행이 없습니다.');
    expect(api.restore).toHaveBeenCalledWith('trip1');
    expect(screen.getByRole('status')).toHaveTextContent('초안으로 복원했습니다.');
  });
  it('목록 조회 실패를 빈 휴지통으로 오인하지 않는다', async () => {
    api.listPage.mockRejectedValueOnce(new Error('network'));
    render(<TripTrash />);
    expect(await screen.findByRole('alert')).toHaveTextContent('불러오지 못했습니다.');
    expect(screen.queryByText('휴지통에 여행이 없습니다.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await screen.findByText('복원할 여행');
  });
  it('cursor로 이전·다음 페이지의 여행에 접근한다', async () => {
    api.listPage.mockResolvedValueOnce({ ...page, has_more: true, cursor: 'page2' })
      .mockResolvedValueOnce({ items: [{ ...trip, trip_id: 'trip2', title: '둘째 여행' }], has_more: false, cursor: null })
      .mockResolvedValueOnce(page);
    render(<TripTrash />);
    await screen.findByText('복원할 여행');
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    await screen.findByText('둘째 여행');
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'page2', trashed: true }));
    fireEvent.click(screen.getByRole('button', { name: '이전' }));
    await screen.findByText('복원할 여행');
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: undefined }));
  });
  it('복원 실패는 원래 행을 보존한다', async () => {
    api.restore.mockRejectedValue(new Error('quota'));
    render(<TripTrash />);
    fireEvent.click(await screen.findByRole('button', { name: '복원할 여행 복원' }));
    await screen.findByRole('alert');
    await waitFor(() => expect(screen.getByRole('button', { name: '복원할 여행 복원' })).toBeEnabled());
    expect(screen.getByText('복원할 여행')).toBeInTheDocument();
  });
});
