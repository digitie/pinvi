import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { TripComments } from '@/components/trips/TripComments';

const api = vi.hoisted(() => ({
  listComments: vi.fn(), listSharedComments: vi.fn(),
  createSharedComment: vi.fn(), deleteSharedComment: vi.fn(), me: vi.fn(),
}));
vi.mock('@pinvi/api-client', async (original) => ({
  ...await original<typeof import('@pinvi/api-client')>(),
  tripApi: () => api, authApi: () => ({ me: api.me }),
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
const comment = {
  comment_id: 'c1', author_user_id: 'author', body: '첫 의견', created_at: '2026-11-03T09:00:00+09:00',
};
beforeEach(() => {
  vi.clearAllMocks();
  api.me.mockResolvedValue({ user_id: 'owner' });
  api.listComments.mockResolvedValue([comment]);
  api.listSharedComments.mockResolvedValue([comment]);
});

describe('댓글 권한과 갱신', () => {
  it('작성자가 아닌 소유자에게도 삭제 버튼을 표시한다', async () => {
    render(<TripComments tripId="t1" ownerUserId="owner" />);
    expect(await screen.findByLabelText('댓글 삭제')).toBeInTheDocument();
  });
  it('comment 이벤트의 refreshKey가 바뀌면 목록을 다시 읽는다', async () => {
    const { rerender } = render(<TripComments tripId="t1" refreshKey={0} />);
    await screen.findByText('첫 의견');
    api.listComments.mockResolvedValue([comment, { ...comment, comment_id: 'c2', body: '새 의견' }]);
    rerender(<TripComments tripId="t1" refreshKey={1} />);
    expect(await screen.findByText('새 의견')).toBeInTheDocument();
    expect(api.me).toHaveBeenCalledTimes(1);
  });
  it('공유 댓글은 토큰 범위 API로 읽고 작성한다', async () => {
    render(<TripComments tripId="t1" sharedToken="share-token" />);
    await screen.findByText('첫 의견');
    fireEvent.change(screen.getByLabelText('댓글 입력'), { target: { value: '공유 의견' } });
    fireEvent.click(screen.getByRole('button', { name: '작성' }));
    await waitFor(() => expect(api.createSharedComment).toHaveBeenCalledWith(
      't1', 'share-token', { body: '공유 의견', target_type: 'trip' },
    ));
    expect(api.listComments).not.toHaveBeenCalled();
  });
});
