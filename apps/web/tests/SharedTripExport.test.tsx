import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { SharedTripView } from '../components/trips/SharedTripView';
import { exportSource } from './fixtures/tripExport';

const mocks = vi.hoisted(() => ({ getShared: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  tripApi: () => mocks,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
vi.mock('@/components/trips/TripMapView', () => ({ TripMapView: () => <div /> }));
vi.mock('@/components/trips/TripPoiList', () => ({ TripPoiList: () => <div /> }));
vi.mock('@/components/trips/TripDayHeader', () => ({ TripDayHeader: () => <div /> }));
vi.mock('@/components/trips/TripComments', () => ({ TripComments: () => <div /> }));
vi.mock('@/components/trips/SharedTripEditor', () => ({ SharedTripEditor: () => <div /> }));
beforeEach(() => vi.clearAllMocks());

it('공유 token 변경 직후 이전 일정·내보내기를 닫고 거절된 새 링크에 재노출하지 않는다', async () => {
  const source = exportSource();
  const id = source.trip.trip_id;
  let rejectLink!: (error: Error) => void;
  mocks.getShared
    .mockResolvedValueOnce({ ...source, visibility: 'view_only', broken_feature_count: 0 })
    .mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectLink = reject;
        }),
    );
  const user = userEvent.setup();
  const { rerender } = render(<SharedTripView tripId={id} token="private-token-a" />);
  await user.click(await screen.findByRole('button', { name: '여행 내보내기' }));
  expect(await screen.findByTestId('trip-export-document')).toHaveTextContent('부산 여행');
  rerender(<SharedTripView tripId={id} token="private-token-b" />);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '여행 내보내기' })).not.toBeInTheDocument();
  expect(screen.queryByText('부산 여행')).not.toBeInTheDocument();
  await act(async () => {
    rejectLink(new Error('denied'));
  });
  expect(await screen.findByTestId('shared-error')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '여행 내보내기' })).not.toBeInTheDocument();
  expect(document.body.textContent).not.toContain('private-token-a');
  expect(document.body.textContent).not.toContain('private-token-b');
});
