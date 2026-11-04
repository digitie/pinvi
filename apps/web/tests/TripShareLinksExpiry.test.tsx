import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TripShareLinks } from '@/components/trips/TripShareLinks';

const api = vi.hoisted(() => ({ createShareToken: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...await original<typeof import('@pinvi/api-client')>(), tripApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

beforeEach(() => vi.clearAllMocks());

describe('공유 링크 만료일 (#626)', () => {
  it('지난 만료일은 요청하지 않고 이유를 알린다', async () => {
    render(<TripShareLinks tripId="00000000-0000-4000-8000-000000000001" shareLinks={[]} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('만료일(선택)'), { target: { value: '2026-01-01' } });
    fireEvent.click(screen.getByRole('button', { name: '링크 만들기' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('만료일은 오늘 이후로 선택해 주세요.');
    expect(api.createShareToken).not.toHaveBeenCalled();
  });

  it('오늘 이후 만료일은 KST 하루 끝으로 보낸다', async () => {
    api.createShareToken.mockResolvedValue({ token: 'tok' });
    render(<TripShareLinks tripId="00000000-0000-4000-8000-000000000001" shareLinks={[]} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('만료일(선택)'), { target: { value: '2099-12-31' } });
    fireEvent.click(screen.getByRole('button', { name: '링크 만들기' }));
    await waitFor(() => expect(api.createShareToken).toHaveBeenCalledWith('00000000-0000-4000-8000-000000000001', {
      visibility: 'view_only', expires_at: '2099-12-31T14:59:59.000Z',
    }));
  });
});
