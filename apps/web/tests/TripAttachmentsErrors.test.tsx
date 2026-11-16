import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { TripAttachments } from '../components/trips/TripAttachments';

const mocks = vi.hoisted(() => ({ listAttachments: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  tripApi: () => mocks,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
beforeEach(() => vi.clearAllMocks());

const textFile = () => new File(['not allowed'], 'blocked.txt', { type: 'text/plain' });

it('늦게 끝난 첫 목록 응답이 그 사이 낸 형식 거부 안내를 지우지 않는다(live POI-023)', async () => {
  let resolveList!: (items: unknown[]) => void;
  mocks.listAttachments.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveList = resolve;
      }),
  );
  render(<TripAttachments tripId="trip-1" />);
  fireEvent.change(screen.getByTestId('attachment-input'), { target: { files: [textFile()] } });
  expect(screen.getByRole('alert')).toHaveTextContent(/^업로드 가능한 파일 형식은 .+입니다\.$/);

  await act(async () => {
    resolveList([]);
  });
  expect(mocks.listAttachments).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('alert')).toHaveTextContent(/^업로드 가능한 파일 형식은 .+입니다\.$/);
});

it('목록 불러오기 실패는 alert로 보인다', async () => {
  mocks.listAttachments.mockRejectedValueOnce(new Error('network'));
  render(<TripAttachments tripId="trip-1" />);
  expect(await screen.findByRole('alert')).toHaveTextContent('첨부를 불러오지 못했습니다.');
});
