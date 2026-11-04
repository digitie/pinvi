import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from '@pinvi/api-client';
import { StorageRetentionPanel } from '@/components/admin/StorageRetentionPanel';

const api = vi.hoisted(() => ({ getStorageRetention: vi.fn(), executeStorageRetention: vi.fn() }));
vi.mock('@pinvi/api-client', async (load) => ({
  ...await load<typeof import('@pinvi/api-client')>(), adminApi: () => api,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
const status = {
  retention_days: 30, expired_trips: 1, eligible_attachments: 1, expired_uploads: 0,
  pending_objects: 0, in_progress_objects: 0, protected_uploads: 0, held_attachments: 0,
  errors: [], can_execute: true,
};
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><StorageRetentionPanel /></QueryClientProvider>);
}
async function confirm() {
  const button = await screen.findByRole('button', { name: '기한 지난 여행·파일 정리' });
  fireEvent.change(screen.getByLabelText('첨부 정리 사유'), { target: { value: 'WSL approved cleanup' } });
  fireEvent.change(screen.getByLabelText(/확인 문구:/), { target: { value: 'DELETE EXPIRED FILES' } });
  fireEvent.click(button);
  fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: '영구 정리 실행' }));
}
beforeEach(() => { vi.clearAllMocks(); api.getStorageRetention.mockResolvedValue(status); });
describe('첨부 정리', () => {
  it('사유·정확한 문구·최종 확인을 거친 뒤 한 번만 실행한다', async () => {
    api.executeStorageRetention.mockResolvedValue({
      expired_trips_started: 1, retired_references: 0, objects_deleted: 1, objects_failed: 0,
      trips_deleted: 1, trip_cleanup_errors: [], status: { ...status, expired_trips: 0, eligible_attachments: 0 },
    });
    setup();
    const button = await screen.findByRole('button', { name: '기한 지난 여행·파일 정리' });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText('첨부 정리 사유'), { target: { value: 'WSL approved cleanup' } });
    fireEvent.change(screen.getByLabelText(/확인 문구:/), { target: { value: 'DELETE' } });
    expect(button).toBeDisabled();
    expect(api.executeStorageRetention).not.toHaveBeenCalled();
    await confirm();
    await waitFor(() => expect(api.executeStorageRetention).toHaveBeenCalledTimes(1));
    expect(api.executeStorageRetention).toHaveBeenCalledWith({ access_reason: 'WSL approved cleanup', confirm_phrase: 'DELETE EXPIRED FILES' });
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });
  it('읽기 전용 운영자는 원인을 보되 실행하지 못한다', async () => {
    api.getStorageRetention.mockResolvedValue({ ...status, can_execute: false, errors: [
      { code: 'AccessDenied:DeleteObject', count: 1, phase: 'delete' },
    ] });
    setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('저장소 삭제 권한');
    expect(screen.queryByRole('button', { name: '기한 지난 여행·파일 정리' })).not.toBeInTheDocument();
  });
  it('실행 오류를 닫히지 않는 확인창 뒤에 숨기지 않는다', async () => {
    api.executeStorageRetention.mockRejectedValue(new ApiError('STORAGE_UNAVAILABLE', '저장소에 연결할 수 없습니다.', 503));
    setup();
    await confirm();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(await screen.findByRole('alert')).toHaveTextContent('저장소에 연결할 수 없습니다.');
  });
  it('삭제 재검증 실패와 최초 삭제 실패의 과금을 구분한다', async () => {
    api.getStorageRetention.mockResolvedValue({ ...status, errors: [
      { code: 'AccessDenied:DeleteObject', count: 1, phase: 'verify' },
    ] });
    setup();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('재확인');
    expect(alert).not.toHaveTextContent('사용 용량을 유지');
  });
});
